locals {
  name = "${var.project_name}-${var.environment}-api"

  # Non-secret env vars, mirroring config.py's Settings class plus the AWS-
  # specific values the S3/RDS/SQS migration (docs/aws-production-
  # architecture.md's "before this is provisioned" section) will consume.
  environment_vars = [
    { name = "AWS_REGION", value = var.aws_region },
    { name = "DASHBOARD_CORS_ORIGINS", value = var.cors_origins },
    { name = "PIPELINE_MAX_CONCURRENCY", value = tostring(var.pipeline_max_concurrency) },
    { name = "PIPELINE_TIMEOUT_SECONDS", value = tostring(var.pipeline_timeout_seconds) },
    { name = "S3_BUCKET_NAME", value = var.s3_bucket_name },
    { name = "SQS_QUEUE_URL", value = var.sqs_queue_url },
    { name = "DB_HOST", value = var.db_host },
    { name = "DB_PORT", value = tostring(var.db_port) },
    { name = "DB_NAME", value = var.db_name },
  ]

  secrets = concat(
    [for key, arn in var.llm_key_parameter_arns : { name = upper(replace(key, "-", "_")), valueFrom = arn }],
    [
      { name = "AUTH_SECRET_KEY", valueFrom = var.jwt_signing_key_parameter_arn },
      { name = "DB_USER", valueFrom = "${var.db_master_secret_arn}:username::" },
      { name = "DB_PASSWORD", valueFrom = "${var.db_master_secret_arn}:password::" },
    ],
  )
}

resource "aws_ecs_task_definition" "this" {
  family                   = local.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.task_role_arn

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = "${var.ecr_repository_url}:${var.image_tag}"
      essential = true

      # docs/aws-production-architecture.md §9: one image, two commands.
      # This is the API entrypoint - unmodified from railway.json's today.
      command = ["uvicorn", "api_app:app", "--host", "0.0.0.0", "--port", tostring(var.container_port)]

      portMappings = [
        { containerPort = var.container_port, protocol = "tcp" }
      ]

      environment = local.environment_vars
      secrets     = local.secrets

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = var.log_group_name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }
      }

      # web_api/routers/system.py's GET /health - confirmed fast under
      # heavy pipeline load by the Phase 1.1 stability work. Uses Python
      # (always present) rather than curl, which ai_video_studio/Dockerfile
      # does not currently install - avoids adding an image dependency just
      # for this check.
      healthCheck = {
        command = [
          "CMD-SHELL",
          "python -c \"import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:${var.container_port}/health', timeout=3).status == 200 else 1)\" || exit 1",
        ]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 15
      }
    }
  ])

  tags = merge(var.tags, { Name = local.name })
}

resource "aws_ecs_service" "this" {
  name            = local.name
  cluster         = var.cluster_arn
  task_definition = aws_ecs_task_definition.this.arn
  desired_count   = var.min_capacity
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.private_subnet_ids
    security_groups = [var.security_group_id]
  }

  load_balancer {
    target_group_arn = var.target_group_arn
    container_name   = "api"
    container_port   = var.container_port
  }

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = 60

  lifecycle {
    ignore_changes = [desired_count] # let autoscaling own this after initial apply
  }

  tags = merge(var.tags, { Name = local.name })
}

resource "aws_appautoscaling_target" "this" {
  service_namespace  = "ecs"
  resource_id        = "service/${var.cluster_name}/${aws_ecs_service.this.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = var.min_capacity
  max_capacity       = var.max_capacity
}

# CPU-based target tracking (docs/aws-production-architecture.md §13):
# reasonable for a mostly I/O-bound FastAPI app, standard and simple.
resource "aws_appautoscaling_policy" "cpu" {
  name               = "${local.name}-cpu-target-tracking"
  service_namespace  = aws_appautoscaling_target.this.service_namespace
  resource_id        = aws_appautoscaling_target.this.resource_id
  scalable_dimension = aws_appautoscaling_target.this.scalable_dimension
  policy_type        = "TargetTrackingScaling"

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 60
    scale_in_cooldown  = 120
    scale_out_cooldown = 60
  }
}
