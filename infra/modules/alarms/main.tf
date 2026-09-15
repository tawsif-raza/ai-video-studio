locals {
  name = "${var.project_name}-${var.environment}"
}

# The exact signal that would have caught the original thread-pool-
# starvation crash mode before a user did (docs/aws-production-
# architecture.md §8).
resource "aws_cloudwatch_metric_alarm" "alb_unhealthy_hosts" {
  alarm_name          = "${local.name}-alb-unhealthy-hosts"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  statistic           = "Maximum"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  period              = 60
  evaluation_periods  = 2
  treat_missing_data  = "notBreaching"
  alarm_description   = "API service has at least one unhealthy target for 2+ minutes"

  dimensions = {
    LoadBalancer = var.alb_arn_suffix
    TargetGroup  = var.api_target_group_arn_suffix
  }

  alarm_actions = [var.sns_topic_arn]
  ok_actions    = [var.sns_topic_arn]
  tags          = var.tags
}

resource "aws_cloudwatch_metric_alarm" "queue_backlog_age" {
  alarm_name          = "${local.name}-queue-backlog-age"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateAgeOfOldestMessage"
  statistic           = "Maximum"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 600 # 10 minutes
  period              = 300
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"
  alarm_description   = "Oldest queued job is over 10 minutes old - worker capacity may not be keeping up"

  dimensions = {
    QueueName = var.sqs_queue_name
  }

  alarm_actions = [var.sns_topic_arn]
  ok_actions    = [var.sns_topic_arn]
  tags          = var.tags
}

resource "aws_cloudwatch_metric_alarm" "dlq_has_messages" {
  alarm_name          = "${local.name}-dlq-has-messages"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  period              = 300
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"
  alarm_description   = "A job failed 3 times and landed in the DLQ - something is failing repeatedly, page a human rather than retry silently"

  dimensions = {
    QueueName = var.sqs_dlq_name
  }

  alarm_actions = [var.sns_topic_arn]
  tags          = var.tags
}

resource "aws_cloudwatch_metric_alarm" "rds_free_storage_low" {
  alarm_name          = "${local.name}-rds-free-storage-low"
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  statistic           = "Minimum"
  comparison_operator = "LessThanThreshold"
  threshold           = 2147483648 # 2 GiB
  period              = 300
  evaluation_periods  = 2
  treat_missing_data  = "breaching"

  dimensions = {
    DBInstanceIdentifier = var.rds_instance_id
  }

  alarm_actions = [var.sns_topic_arn]
  tags          = var.tags
}

resource "aws_cloudwatch_metric_alarm" "rds_cpu_high" {
  alarm_name          = "${local.name}-rds-cpu-high"
  namespace           = "AWS/RDS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 80
  period              = 300
  evaluation_periods  = 3

  dimensions = {
    DBInstanceIdentifier = var.rds_instance_id
  }

  alarm_actions = [var.sns_topic_arn]
  tags          = var.tags
}

resource "aws_cloudwatch_metric_alarm" "api_cpu_high" {
  alarm_name          = "${local.name}-api-cpu-high"
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 85
  period              = 300
  evaluation_periods  = 3

  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.ecs_api_service_name
  }

  alarm_actions = [var.sns_topic_arn]
  tags          = var.tags
}

resource "aws_cloudwatch_metric_alarm" "worker_memory_high" {
  alarm_name          = "${local.name}-worker-memory-high"
  namespace           = "AWS/ECS"
  metric_name         = "MemoryUtilization"
  statistic           = "Average"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 90
  period              = 300
  evaluation_periods  = 2
  alarm_description   = "Worker tasks running hot on memory - the exact signal for an ffmpeg job sized wrong for the task"

  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.ecs_worker_service_name
  }

  alarm_actions = [var.sns_topic_arn]
  tags          = var.tags
}
