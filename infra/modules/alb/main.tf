locals {
  name      = "${var.project_name}-${var.environment}"
  has_https = var.certificate_arn != ""
}

resource "aws_lb" "this" {
  name               = "${local.name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.security_group_id]
  subnets            = var.public_subnet_ids

  enable_deletion_protection = var.deletion_protection
  drop_invalid_header_fields = true

  tags = merge(var.tags, { Name = "${local.name}-alb" })
}

# GET /health (web_api/routers/system.py) - confirmed in the Phase 1.1
# stability work to stay fast even under heavy pipeline load, which is
# exactly the property this health check depends on.
resource "aws_lb_target_group" "api" {
  name        = "${local.name}-api"
  port        = var.container_port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip" # required for awsvpc-networked Fargate tasks

  health_check {
    enabled             = true
    path                = "/health"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 15
    matcher             = "200"
  }

  deregistration_delay = 30

  tags = merge(var.tags, { Name = "${local.name}-api" })
}

resource "aws_lb_listener" "https" {
  count             = local.has_https ? 1 : 0
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = local.has_https ? "redirect" : "forward"

    dynamic "redirect" {
      for_each = local.has_https ? [1] : []
      content {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }

    target_group_arn = local.has_https ? null : aws_lb_target_group.api.arn
  }
}
