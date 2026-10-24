#!/usr/bin/env bash
set -u

M=/opt/nvidia/deepstream/deepstream/samples/models
status=0

for f in \
  Primary_Detector/resnet18_trafficcamnet_pruned.onnx \
  Primary_Detector/labels.txt \
  Secondary_VehicleTypes/resnet18_vehicletypenet_pruned.onnx \
  Secondary_VehicleTypes/labels.txt
do
  if [ -f "$M/$f" ]; then
    echo "OK      $f"
  else
    echo "MISSING $f"
    status=1
  fi
done

mkdir -p /opt/vds/engines
exit "$status"
