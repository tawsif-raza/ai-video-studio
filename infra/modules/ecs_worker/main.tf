locals {
  name = "${var.project_name}-${var.environment}-worker"

  environment_vars = [
    { name = "AWS_REGION", value = var.aws_region },
    { name = "SQS_QUEUE_URL", value = var.sqs_queue_url },
    { name = "PIPELINE_MAX_CONCURRENCY", value = tostring(var.pipeline_max_concurrency) },
    { name = "PIPELINE_TIMEOUT_SECONDS", value = tostring(var.pipeline_timeout_seconds) },
    { name = "S3_BUCKET_NAME", value = var.s3_bucket_name },
    { name = "DB_HOST", value = var.db_host },
    { name = "DB_PORT", value = tostring(var.db_port) },
    { name = "DB_NAME", value = var.db_name },
  ]

  secrets = concat(
    [for key, arn in var.llm_key_parameter_arns : { name = upper(replace(key, "-", "_")), valueFrom = arn }],
    [
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
      name      = "worker"
      image     = "${var.ecr_repository_url}:${var.image_tag}"
      essential = true

      # docs/aws-production-architecture.md §4/§9: one image, two commands.
      # `worker.py` is the SQS poll loop that dispatches to the existing,
      # unmodified run_director_pipeline/run_producer_pipeline/
      # run_render_pipeline/run_publish_pipeline functions
      # (web_api/{director,producer,render,publish}_runner.py) - it does
      # NOT exist in the codebase yet (see §4's "this is a real code
      # change, not just infrastructure"). This task definition is correct
      # for when it lands; do not point desired_count above 0 before then.
      command = ["python", "worker.py"]

      environment = local.environment_vars
      secrets     = local.secrets

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = var.log_group_name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "worker"
        }
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

  dynamic "capacity_provider_strategy" {
    for_each = var.use_fargate_spot ? [1] : []
    content {
      capacity_provider = "FARGATE_SPOT"
      weight            = 1
    }
  }

  # Falls back to standard Fargate if Spot is disabled - never mix both in
  # one strategy block set for this service, keeps behavior predictable.
  dynamic "capacity_provider_strategy" {
    for_each = var.use_fargate_spot ? [] : [1]
    content {
      capacity_provider = "FARGATE"
      weight            = 1
    }
  }

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.security_group_id]
    assign_public_ip = false
  }

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

# Step scaling on SQS backlog (docs/aws-production-architecture.md §13):
# scale out as the queue grows, back to 0 when it's empty - the AWS-native
# version of the same "bounded, queued, doesn't let one heavy user starve
# everyone else" property PipelineExecutor already built at the
# application level (docs/phase1.1-p0-fixes.md), with the added benefit of
# being able to add capacity instead of just queuing longer.

resource "aws_appautoscaling_policy" "scale_out" {
  name               = "${local.name}-scale-out"
  service_namespace  = aws_appautoscaling_target.this.service_namespace
  resource_id        = aws_appautoscaling_target.this.resource_id
  scalable_dimension = aws_appautoscaling_target.this.scalable_dimension
  policy_type        = "StepScaling"

  step_scaling_policy_configuration {
    adjustment_type         = "ChangeInCapacity"
    cooldown                = 60
    metric_aggregation_type = "Maximum"

    step_adjustment {
      metric_interval_lower_bound = 0
      scaling_adjustment          = 2
    }
  }
}

resource "aws_appautoscaling_policy" "scale_in" {
  name               = "${local.name}-scale-in"
  service_namespace  = aws_appautoscaling_target.this.service_namespace
  resource_id        = aws_appautoscaling_target.this.resource_id
  scalable_dimension = aws_appautoscaling_target.this.scalable_dimension
  policy_type        = "StepScaling"

  step_scaling_policy_configuration {
    adjustment_type         = "ExactCapacity"
    cooldown                = 300
    metric_aggregation_type = "Maximum"

    step_adjustment {
      metric_interval_upper_bound = 0
      scaling_adjustment          = var.min_capacity
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "queue_has_backlog" {
  alarm_name          = "${local.name}-queue-has-backlog"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  period              = 60
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = var.sqs_queue_name
  }

  alarm_actions = [aws_appautoscaling_policy.scale_out.arn]
  tags          = merge(var.tags, { Name = "${local.name}-queue-has-backlog" })
}

resource "aws_cloudwatch_metric_alarm" "queue_is_empty" {
  alarm_name          = "${local.name}-queue-is-empty"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  period              = 300
  evaluation_periods  = 3           # empty for 15 minutes before scaling back down
  treat_missing_data  = "breaching" # no messages published = treat as empty

  dimensions = {
    QueueName = var.sqs_queue_name
  }

  alarm_actions = [aws_appautoscaling_policy.scale_in.arn]
  tags          = merge(var.tags, { Name = "${local.name}-queue-is-empty" })
}
