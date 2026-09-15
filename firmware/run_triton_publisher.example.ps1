# Copy this file beside the production publisher, remove ".example" from its
# name, and replace every CHANGE_ME value before creating the scheduled task.
$ErrorActionPreference = "Stop"

$publisherDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$tritonLogDirectory = "C:\CHANGE_ME\Triton\LogFiles"
$brokerName = "labpulse-pi.local"
$mqttTopic = "labpulse/triton/CHANGE_ME_FRIDGE_ID/measurements"
$heartbeatTopic = "labpulse/triton/CHANGE_ME_FRIDGE_ID/heartbeat"
$mqttUsername = "CHANGE_ME_TRITON_USERNAME"
$passwordFile = Join-Path $publisherDirectory "mqtt-password.txt"
$caCertificate = Join-Path $publisherDirectory "labpulse-ca.crt"
$operationalLog = Join-Path $publisherDirectory "triton-publisher.log"

& py -3 (Join-Path $publisherDirectory "triton_logfile_publisher_production.py") `
    --directory $tritonLogDirectory `
    --broker $brokerName `
    --port 8883 `
    --topic $mqttTopic `
    --heartbeat-topic $heartbeatTopic `
    --username $mqttUsername `
    --password-file $passwordFile `
    --ca-certificate $caCertificate `
    --log-file $operationalLog

if ($LASTEXITCODE -ne 0) {
    throw "Triton logfile publisher exited with code $LASTEXITCODE"
}
