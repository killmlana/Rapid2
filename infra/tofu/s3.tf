resource "aws_s3_bucket" "papers" {
  bucket        = "${var.project_name}-papers-${data.aws_caller_identity.current.account_id}"
  force_destroy = var.environment == "dev"

  tags = { Name = "${var.project_name}-papers" }
}

resource "aws_s3_bucket_versioning" "papers" {
  bucket = aws_s3_bucket.papers.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "papers" {
  bucket = aws_s3_bucket.papers.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "papers" {
  bucket = aws_s3_bucket.papers.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
