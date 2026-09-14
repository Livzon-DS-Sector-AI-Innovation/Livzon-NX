group "release" {
  targets = ["backend", "frontend", "hermes"]
}

target "backend" {
  context    = "."
  dockerfile = "Dockerfile"
  target     = "backend"
  platforms  = ["linux/amd64"]
}

target "frontend" {
  context    = "."
  dockerfile = "Dockerfile"
  target     = "frontend"
  platforms  = ["linux/amd64"]
}

target "hermes" {
  context    = "."
  dockerfile = "Dockerfile"
  target     = "hermes"
  platforms  = ["linux/amd64"]
}
