resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_cloudwatch_log_group" "grobid" {
  name              = "/ecs/${var.project_name}/grobid"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "vila" {
  name              = "/ecs/${var.project_name}/vila"
  retention_in_days = 14
}

# --- GROBID on Fargate (CPU only) ---

resource "aws_ecs_task_definition" "grobid" {
  family                   = "${var.project_name}-grobid"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.grobid_cpu
  memory                   = var.grobid_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "grobid"
    image     = "${aws_ecr_repository.grobid.repository_url}:latest"
    essential = true

    portMappings = [{
      containerPort = 8070
      protocol      = "tcp"
    }]

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8070/api/isalive || exit 1"]
      interval    = 30
      timeout     = 10
      retries     = 3
      startPeriod = 60
    }

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.grobid.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "grobid"
      }
    }
  }])
}

resource "aws_ecs_service" "grobid" {
  name            = "${var.project_name}-grobid"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.grobid.arn
  desired_count   = var.grobid_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.ecs_services.id]
  }

  service_connect_configuration {
    enabled   = true
    namespace = aws_service_discovery_private_dns_namespace.main.arn

    service {
      port_name      = "grobid"
      discovery_name = "grobid"
      client_alias {
        port     = 8070
        dns_name = "grobid.rapid2.local"
      }
    }
  }
}

# --- VILA on EC2 with GPU ---

data "aws_ssm_parameter" "ecs_gpu_ami" {
  name = "/aws/service/ecs/optimized-ami/amazon-linux-2/gpu/recommended/image_id"
}

resource "aws_launch_template" "vila_gpu" {
  name_prefix   = "${var.project_name}-vila-gpu-"
  image_id      = data.aws_ssm_parameter.ecs_gpu_ami.value
  instance_type = var.vila_gpu_instance_type

  iam_instance_profile {
    arn = aws_iam_instance_profile.ecs_instance.arn
  }

  network_interfaces {
    security_groups             = [aws_security_group.ecs_services.id]
    associate_public_ip_address = false
  }

  user_data = base64encode(<<-EOF
    #!/bin/bash
    echo "ECS_CLUSTER=${aws_ecs_cluster.main.name}" >> /etc/ecs/ecs.config
    echo "ECS_ENABLE_GPU_SUPPORT=true" >> /etc/ecs/ecs.config
  EOF
  )

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name = "${var.project_name}-vila-gpu"
    }
  }
}

resource "aws_autoscaling_group" "vila_gpu" {
  name_prefix         = "${var.project_name}-vila-gpu-"
  desired_capacity    = var.vila_desired_count
  min_size            = 0
  max_size            = 3
  vpc_zone_identifier = aws_subnet.private[*].id

  launch_template {
    id      = aws_launch_template.vila_gpu.id
    version = "$Latest"
  }

  tag {
    key                 = "AmazonECSManaged"
    value               = true
    propagate_at_launch = true
  }
}

resource "aws_ecs_capacity_provider" "vila_gpu" {
  name = "${var.project_name}-vila-gpu"

  auto_scaling_group_provider {
    auto_scaling_group_arn         = aws_autoscaling_group.vila_gpu.arn
    managed_termination_protection = "DISABLED"

    managed_scaling {
      status          = "ENABLED"
      target_capacity = 100
    }
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", aws_ecs_capacity_provider.vila_gpu.name]
}

resource "aws_ecs_task_definition" "vila" {
  family                   = "${var.project_name}-vila"
  requires_compatibilities = ["EC2"]
  network_mode             = "awsvpc"
  cpu                      = 4096
  memory                   = 15360
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "vila"
    image     = "${aws_ecr_repository.vila.repository_url}:latest"
    essential = true
    gpu       = 1

    portMappings = [{
      containerPort = 8080
      name          = "vila"
      protocol      = "tcp"
    }]

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8080/ || exit 1"]
      interval    = 30
      timeout     = 10
      retries     = 3
      startPeriod = 120
    }

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.vila.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "vila"
      }
    }

    resourceRequirements = [{
      type  = "GPU"
      value = "1"
    }]
  }])
}

resource "aws_ecs_service" "vila" {
  name            = "${var.project_name}-vila"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.vila.arn
  desired_count   = var.vila_desired_count

  capacity_provider_strategy {
    capacity_provider = aws_ecs_capacity_provider.vila_gpu.name
    weight            = 1
  }

  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.ecs_services.id]
  }

  service_connect_configuration {
    enabled   = true
    namespace = aws_service_discovery_private_dns_namespace.main.arn

    service {
      port_name      = "vila"
      discovery_name = "vila"
      client_alias {
        port     = 8080
        dns_name = "vila.rapid2.local"
      }
    }
  }
}

# Service discovery namespace for internal DNS
resource "aws_service_discovery_private_dns_namespace" "main" {
  name = "rapid2.local"
  vpc  = aws_vpc.main.id
}
