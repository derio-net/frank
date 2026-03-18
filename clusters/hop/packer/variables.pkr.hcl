variable "hcloud_token" {
  type      = string
  sensitive = true
}

variable "talos_image_path" {
  type        = string
  description = "Local path to the Talos raw image downloaded from Omni dashboard (Hetzner variant)"
}

variable "location" {
  type    = string
  default = "fsn1"
}

variable "server_type" {
  type    = string
  default = "cx23"
}

variable "snapshot_name" {
  type    = string
  default = "talos-omni-hop"
}
