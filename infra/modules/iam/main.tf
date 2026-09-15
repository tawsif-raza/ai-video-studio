locals {
  name = "${var.project_name}-${var.environment}"
}

data "aws_iam_policy_document" "ecs_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# --- Shared task EXECUTION role: what the ECS agent itself uses to pull the
# image and resolve `secrets` into container env vars at startup. Separate
# from the TASK roles below, which are what the running application code
# uses at runtime. ---

resource "aws_iam_role" "execution" {
  name               = "${local.name}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
  tags               = merge(var.tags, { Name = "${local.name}-ecs-execution" })
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  statement {
    sid       = "PullImage"
    effect    = "Allow"
    actions   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    resources = [var.ecr_repository_arn]
  }

  # ecr:GetAuthorizationToken has no resource-level permissions in the IAM
  # policy language - AWS requires Resource "*" for this specific action.
  statement {
    sid       = "EcrAuth"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid    = "ReadSecretsForContainerInjection"
    effect = "Allow"
    actions = [
      "ssm:GetParameters",
      "secretsmanager:GetSecretValue",
    ]
    resources = concat(
      values(var.llm_key_parameter_arns),
      [var.jwt_signing_key_parameter_arn, var.rds_master_secret_arn],
    )
  }

  # Both AWS-managed keys (aws/ssm, aws/secretsmanager) are referenced via
  # a kms:ViaService condition rather than a direct key ARN lookup - not
  # just a style choice. AWS creates these keys lazily, the first time each
  # service is actually used to store something with default encryption in
  # an account/region; on a fresh account (confirmed against this one:
  # alias/aws/secretsmanager did not exist pre-apply, only alias/aws/ssm
  # did), a `data "aws_kms_alias"` lookup for the not-yet-created one fails
  # at plan time. The Resource "*" here is scoped tightly by the condition,
  # not actually broad: it only ever matches a KMS call routed through the
  # named service, in this account, in this region - it cannot decrypt an
  # unrelated customer-managed key.
  statement {
    sid       = "DecryptAwsManagedServiceKeys"
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values = [
        "ssm.${data.aws_region.current.name}.amazonaws.com",
        "secretsmanager.${data.aws_region.current.name}.amazonaws.com",
      ]
    }
  }
}

data "aws_region" "current" {}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "${local.name}-ecs-execution-secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}

# --- API task role: what the running FastAPI app calls AWS with -
# S3 (media/packages), SQS SendMessage only (it enqueues jobs, never
# consumes them - docs/aws-production-architecture.md §4/§10). ---

resource "aws_iam_role" "api_task" {
  name               = "${local.name}-api-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
  tags               = merge(var.tags, { Name = "${local.name}-api-task" })
}

data "aws_iam_policy_document" "api_task" {
  statement {
    sid    = "MediaBucketReadWrite"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]
    resources = [var.s3_bucket_arn, "${var.s3_bucket_arn}/*"]
  }

  statement {
    sid       = "UseMediaBucketKmsKey"
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [var.s3_kms_key_arn]
  }

  statement {
    sid       = "EnqueueJobs"
    effect    = "Allow"
    actions   = ["sqs:SendMessage", "sqs:GetQueueAttributes"]
    resources = [var.sqs_queue_arn]
  }

  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = var.log_group_arns
  }
}

resource "aws_iam_role_policy" "api_task" {
  name   = "${local.name}-api-task"
  role   = aws_iam_role.api_task.id
  policy = data.aws_iam_policy_document.api_task.json
}

# --- Worker task role: S3 read/write + SQS consume (ReceiveMessage/
# DeleteMessage/ChangeMessageVisibility) on the jobs queue only - never the
# DLQ directly (redrive is an operator action, not a runtime one). ---

resource "aws_iam_role" "worker_task" {
  name               = "${local.name}-worker-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
  tags               = merge(var.tags, { Name = "${local.name}-worker-task" })
}

data "aws_iam_policy_document" "worker_task" {
  statement {
    sid    = "MediaBucketReadWrite"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]
    resources = [var.s3_bucket_arn, "${var.s3_bucket_arn}/*"]
  }

  statement {
    sid       = "UseMediaBucketKmsKey"
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [var.s3_kms_key_arn]
  }

  statement {
    sid    = "ConsumeJobs"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:ChangeMessageVisibility",
      "sqs:GetQueueAttributes",
    ]
    resources = [var.sqs_queue_arn]
  }

  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = var.log_group_arns
  }
}

resource "aws_iam_role_policy" "worker_task" {
  name   = "${local.name}-worker-task"
  role   = aws_iam_role.worker_task.id
  policy = data.aws_iam_policy_document.worker_task.json
}
