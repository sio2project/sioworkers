#!/bin/bash
set -e
set -C

LOG_DIR="logs_$(date +"%Y-%m-%d_%H-%M-%S")";
mkdir "$LOG_DIR";

for name in "$@";
do
	echo "Creating machine $name."
	./create_docker_judge_do.sh "$name" &> "$LOG_DIR"/"$name".log  &
done
