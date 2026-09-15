locals {
  name = "${var.project_name}-${var.environment}"

  # /20 per subnet inside a /16 VPC - comfortably large for 2 ECS services,
  # RDS, and an ALB, without carving up the VPC into more pieces than this
  # architecture needs (docs/aws-production-architecture.md §2: 2 AZs,
  # public subnets for the ALB only, private subnets for everything else).
  public_subnet_cidrs  = [cidrsubnet(var.vpc_cidr, 4, 0), cidrsubnet(var.vpc_cidr, 4, 1)]
  private_subnet_cidrs = [cidrsubnet(var.vpc_cidr, 4, 2), cidrsubnet(var.vpc_cidr, 4, 3)]
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, { Name = local.name })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = merge(var.tags, { Name = local.name })
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.this.id
  cidr_block              = local.public_subnet_cidrs[count.index]
  availability_zone       = var.azs[count.index]
  map_public_ip_on_launch = true

  tags = merge(var.tags, { Name = "${local.name}-public-${var.azs[count.index]}", Tier = "public" })
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.this.id
  cidr_block        = local.private_subnet_cidrs[count.index]
  availability_zone = var.azs[count.index]

  tags = merge(var.tags, { Name = "${local.name}-private-${var.azs[count.index]}", Tier = "private" })
}

# --- NAT: one by default, a second only if enable_second_nat_gateway=true ---

resource "aws_eip" "nat" {
  count  = var.enable_second_nat_gateway ? 2 : 1
  domain = "vpc"
  tags   = merge(var.tags, { Name = "${local.name}-nat-${count.index}" })
}

resource "aws_nat_gateway" "this" {
  count         = var.enable_second_nat_gateway ? 2 : 1
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id
  tags          = merge(var.tags, { Name = "${local.name}-nat-${count.index}" })

  depends_on = [aws_internet_gateway.this]
}

# --- Routing ---

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  tags   = merge(var.tags, { Name = "${local.name}-public" })
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# One private route table per AZ if second NAT is enabled (true AZ-isolated
# egress); otherwise both private subnets share one table pointed at the
# single NAT Gateway.
resource "aws_route_table" "private" {
  count  = var.enable_second_nat_gateway ? 2 : 1
  vpc_id = aws_vpc.this.id
  tags   = merge(var.tags, { Name = "${local.name}-private-${count.index}" })
}

resource "aws_route" "private_nat" {
  count                  = var.enable_second_nat_gateway ? 2 : 1
  route_table_id         = aws_route_table.private[count.index].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[count.index].id
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = var.enable_second_nat_gateway ? aws_route_table.private[count.index].id : aws_route_table.private[0].id
}

# --- VPC endpoints (docs/aws-production-architecture.md §2): lets the API
# service reach S3/SQS/Secrets/CloudWatch without any NAT Gateway at all,
# since (once the worker split lands) it never calls external LLM APIs
# directly. Gateway endpoint (S3) is free; interface endpoints cost ~$7.30/
# month each but are what make "API service needs no NAT" true. ---

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${data.aws_region.current.name}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = concat([aws_route_table.public.id], aws_route_table.private[*].id)
  tags              = merge(var.tags, { Name = "${local.name}-s3" })
}

resource "aws_security_group" "vpc_endpoints" {
  name_prefix = "${local.name}-vpce-"
  description = "Allow HTTPS from inside the VPC to interface VPC endpoints"
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "HTTPS from within the VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${local.name}-vpce" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_endpoint" "interface" {
  # ecr.api/ecr.dkr: found missing during the actual staging deployment -
  # a Fargate task's image pull goes through its own ENI (the task's VPC
  # networking), not some separate AWS-managed path, so a private-subnet
  # task with no NAT/internet egress (api_allow_internet_egress=false,
  # this module's default) has no way to reach ECR at all without these -
  # confirmed by a real task stuck in PENDING with no error surfaced yet
  # (ECS eventually times it out as CannotPullContainerError) until these
  # were added. ecr.dkr is what actually serves image layers (registry
  # v2 protocol); ecr.api is used for the auth/metadata calls
  # (GetAuthorizationToken etc.) that precede the pull.
  # ssm: also found missing during the actual staging deployment, distinct
  # from secretsmanager above - LLM keys and the JWT signing key
  # (modules/secrets) live in SSM Parameter Store, a different service
  # from Secrets Manager (only RDS's master password uses that one). The
  # execution role's `ssm:GetParameters` call to resolve them into
  # container env vars at startup needs this endpoint just as much as
  # secretsmanager needs its own - confirmed by a real ECS service event:
  # "unable to retrieve secrets from ssm: ... context deadline exceeded".
  for_each = toset(["sqs", "secretsmanager", "ssm", "logs", "ecr.api", "ecr.dkr"])
  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.${each.value}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = merge(var.tags, { Name = "${local.name}-${each.value}" })
}

data "aws_region" "current" {}
