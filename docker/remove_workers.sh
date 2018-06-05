#!/bin/bash
set -e
set -C

LOG_DIR="logs_$(date +"%Y-%m-%d_%H-%M-%S")";
mkdir "$LOG_DIR";

for name in "$@";
do
	instance=spr4g-"$name"
	echo "Removing machine $instance."
	(! docker-machine stop "$instance"; docker-machine rm -y "$instance";) &>  "$LOG_DIR"/"$instance".log &
done
