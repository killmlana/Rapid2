resource "aws_ecr_repository" "grobid" {
  name                 = "${var.project_name}/grobid"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "vila" {
  name                 = "${var.project_name}/vila"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "web" {
  name                 = "${var.project_name}/web"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

locals {
  ecr_repos = {
    grobid = aws_ecr_repository.grobid.name
    vila   = aws_ecr_repository.vila.name
    web    = aws_ecr_repository.web.name
  }
}

resource "aws_ecr_lifecycle_policy" "cleanup" {
  for_each   = local.ecr_repos
  repository = each.value

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 5 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}
