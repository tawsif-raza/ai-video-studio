locals {
  name = "${var.project_name}-${var.environment}"
}

# --- ALB: only SG in this app with any internet-facing ingress at all.
# var.alb_ingress_cidrs defaults to 0.0.0.0/0 (real production, once
# security checks have passed) but staging deliberately overrides this to
# a specific IP/CIDR - "do not expose the staging environment publicly
# until security checks pass" is enforced here, not just documented. ---

resource "aws_security_group" "alb" {
  name_prefix = "${local.name}-alb-"
  description = "ALB - HTTPS (and HTTP for redirect) from var.alb_ingress_cidrs only"
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = var.alb_ingress_cidrs
  }

  ingress {
    description = "HTTP (redirected to HTTPS by the listener, see module.alb)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = var.alb_ingress_cidrs
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${local.name}-alb" })

  lifecycle {
    create_before_destroy = true
  }
}

# --- API service: only reachable from the ALB. No inbound from the
# internet, ever (docs/aws-production-architecture.md §2/§10). ---

resource "aws_security_group" "api" {
  name_prefix = "${local.name}-api-"
  description = "ECS API service - inbound from ALB only"
  vpc_id      = var.vpc_id

  ingress {
    description     = "From the ALB"
    from_port       = var.container_port
    to_port         = var.container_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  # No inline egress blocks on this resource - all of this SG's egress rules
  # are standalone aws_security_group_rule resources below (api_to_*). Found
  # the hard way during the actual staging deployment: mixing inline
  # ingress/egress blocks with separate aws_security_group_rule resources
  # FOR THE SAME DIRECTION ON THE SAME SG is an explicit AWS-provider
  # conflict - the inline blocks are treated as the complete authoritative
  # rule set on every apply, so a same-SG aws_security_group_rule declared
  # alongside them gets silently revoked. That's exactly what happened to
  # aws_security_group_rule.api_to_rds/worker_to_rds further below: created
  # once, then wiped out by this resource's own inline egress blocks (which
  # used to exist here), leaving the API/worker tasks with no egress path to
  # RDS at all - manifesting as psycopg_pool.PoolTimeout after 30s (the TCP
  # SYN never gets a response) rather than any DNS/auth/application error.
  # (Egress to RDS can't simply move inline here either - an inline block
  # would need security_groups = [aws_security_group.rds.id], and rds's own
  # inline ingress already references aws_security_group.api.id, which is a
  # real dependency cycle. Standalone rules for all of api's egress avoids
  # both problems at once.)

  tags = merge(var.tags, { Name = "${local.name}-api" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group_rule" "api_to_vpc_endpoints" {
  type                     = "egress"
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  security_group_id        = aws_security_group.api.id
  source_security_group_id = var.vpc_endpoints_sg_id
  description              = "To VPC interface endpoints (SQS/Secrets Manager/CloudWatch Logs)"
}

resource "aws_security_group_rule" "api_to_internet" {
  count             = var.api_allow_internet_egress ? 1 : 0
  type              = "egress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  security_group_id = aws_security_group.api.id
  cidr_blocks       = ["0.0.0.0/0"]
  description       = "TRANSITIONAL: unmodified app image still calls LLM providers directly from the API process - see variable description"
}

# --- Worker service: no inbound at all (it polls SQS, nothing calls it).
# Needs broad outbound - it talks to arbitrary third-party LLM/YouTube APIs
# whose IP ranges aren't practical to allowlist. ---

resource "aws_security_group" "worker" {
  name_prefix = "${local.name}-worker-"
  description = "ECS worker service - no inbound; outbound to LLM/YouTube APIs via NAT"
  vpc_id      = var.vpc_id

  # No inline egress blocks here either - see aws_security_group.api's
  # comment above. worker_to_internet/worker_to_rds below are this SG's
  # complete egress rule set.

  tags = merge(var.tags, { Name = "${local.name}-worker" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group_rule" "worker_to_internet" {
  type              = "egress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  security_group_id = aws_security_group.worker.id
  cidr_blocks       = ["0.0.0.0/0"]
  description       = "HTTPS to external LLM providers, YouTube, and AWS services"
}

# --- RDS: inbound 5432 from the API and worker services only. Never
# public (docs/aws-production-architecture.md §2/§10 - "no ECS task, and
# no RDS instance, is ever directly internet-reachable"). ---

resource "aws_security_group" "rds" {
  name_prefix = "${local.name}-rds-"
  description = "RDS PostgreSQL - inbound from API/worker services only, never public"
  vpc_id      = var.vpc_id

  ingress {
    description     = "PostgreSQL from the API service"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.api.id]
  }

  ingress {
    description     = "PostgreSQL from the worker service"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.worker.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${local.name}-rds" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group_rule" "api_to_rds" {
  type                     = "egress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.api.id
  source_security_group_id = aws_security_group.rds.id
  description              = "To RDS PostgreSQL"
}

resource "aws_security_group_rule" "worker_to_rds" {
  type                     = "egress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.worker.id
  source_security_group_id = aws_security_group.rds.id
  description              = "To RDS PostgreSQL"
}
