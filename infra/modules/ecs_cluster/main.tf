locals {
  name = "${var.project_name}-${var.environment}"
}

resource "aws_ecs_cluster" "this" {
  name = local.name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = merge(var.tags, { Name = local.name })
}

# Fargate + Fargate Spot both available to services in this cluster - the
# worker service uses Spot (docs/aws-production-architecture.md §12); the
# API service stays on standard Fargate (see ecs_api module).
resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name       = aws_ecs_cluster.this.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }
}
