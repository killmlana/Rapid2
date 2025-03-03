# ALB for public web access
resource "aws_lb" "web" {
  name               = "${var.project_name}-web"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  tags = { Name = "${var.project_name}-web-alb" }
}

resource "aws_lb_target_group" "web" {
  name        = "${var.project_name}-web"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/api/health"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
    matcher             = "200"
  }
}

resource "aws_lb_listener" "web" {
  load_balancer_arn = aws_lb.web.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }
}

# Web ECS service on Fargate
resource "aws_cloudwatch_log_group" "web" {
  name              = "/ecs/${var.project_name}/web"
  retention_in_days = 14
}

resource "aws_ecs_task_definition" "web" {
  family                   = "${var.project_name}-web"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024
  memory                   = 2048
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "web"
    image     = "${aws_ecr_repository.web.repository_url}:latest"
    essential = true

    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]

    environment = [
      { name = "AWS_REGION", value = var.aws_region },
      { name = "NEPTUNE_ENDPOINT", value = aws_neptune_cluster.main.endpoint },
      { name = "NEPTUNE_PORT", value = tostring(aws_neptune_cluster.main.port) },
      { name = "OPENSEARCH_ENDPOINT", value = aws_opensearch_domain.papers.endpoint },
      { name = "ANNAS_OPENSEARCH_ENDPOINT", value = aws_opensearch_domain.annas_metadata.endpoint },
      { name = "GROBID_URL", value = "http://grobid.rapid2.local:8070" },
      { name = "VILA_URL", value = "http://vila.rapid2.local:8080" },
      { name = "S3_PAPERS_BUCKET", value = aws_s3_bucket.papers.id },
    ]

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8000/api/health || exit 1"]
      interval    = 15
      timeout     = 5
      retries     = 3
      startPeriod = 30
    }

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.web.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "web"
      }
    }
  }])
}

resource "aws_ecs_service" "web" {
  name            = "${var.project_name}-web"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.web.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.ecs_services.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.web.arn
    container_name   = "web"
    container_port   = 8000
  }

  service_connect_configuration {
    enabled   = true
    namespace = aws_service_discovery_private_dns_namespace.main.arn
  }
}
