#!/bin/bash
until python3 nabbot.py; do
	echo "NabBot crashed... Restarting" >&2
	sleep 3
done