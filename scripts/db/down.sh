#!/usr/bin/env sh
set -eu

. "$(dirname -- "$0")/compose_env.sh"

require_docker_compose

docker_compose down
