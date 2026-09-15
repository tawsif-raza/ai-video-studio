output "vpc_id" {
  value = aws_vpc.this.id
}

output "vpc_cidr" {
  value = var.vpc_cidr
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "nat_gateway_ids" {
  value = aws_nat_gateway.this[*].id
}

output "vpc_endpoints_sg_id" {
  value = aws_security_group.vpc_endpoints.id
}
