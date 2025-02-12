output "neptune_endpoint" {
  value = aws_neptune_cluster.main.endpoint
}

output "neptune_port" {
  value = aws_neptune_cluster.main.port
}

output "opensearch_papers_endpoint" {
  value = aws_opensearch_domain.papers.endpoint
}

output "opensearch_annas_endpoint" {
  value = aws_opensearch_domain.annas_metadata.endpoint
}

output "ecr_grobid_url" {
  value = aws_ecr_repository.grobid.repository_url
}

output "ecr_vila_url" {
  value = aws_ecr_repository.vila.repository_url
}

output "grobid_service_dns" {
  value = "grobid.rapid2.local:8070"
}

output "vila_service_dns" {
  value = "vila.rapid2.local:8080"
}

output "s3_papers_bucket" {
  value = aws_s3_bucket.papers.id
}

output "vpc_id" {
  value = aws_vpc.main.id
}
