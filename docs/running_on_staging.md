# Run on Staging

This guide shows how to run the Sluice subnet against a local Bittensor chain for development.

Use this path first if you are changing protocol, scoring, sandbox, or registration behavior.

For role-specific expectations, see [Miner and Validator Guide](miner_validator_guide.md).

## What This Runbook Covers

- building a local Subtensor chain
- registering a subnet locally
- registering miner and validator hotkeys
- running the Sluice miner and validator against that local chain

## Prerequisites

- Python environment with this repo installed
- Docker on the validator machine
- Rust toolchain and Subtensor build dependencies
- `btcli`

The exact `btcli` argument spellings can vary by release. If your local CLI differs, prefer the form shown in `btcli --help`.

## 1. Start a local Subtensor chain

Clone and build Subtensor:

```bash
git clone https://github.com/opentensor/subtensor.git
cd subtensor
./scripts/init.sh
cargo build -p node-subtensor --profile production --features pow-faucet
BUILD_BINARY=0 ./scripts/localnet.sh
```

Leave the chain running in a dedicated terminal.

This guide assumes the local chain endpoint is:

```bash
ws://127.0.0.1:9946
```

## 2. Prepare this repository

In a second terminal:

```bash
cd /path/to/sluice-subnet-core
python -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env.miner
cp .env.example .env.validator
```

Build the sample router artifact:

```bash
python -m sluice.router.builder \
  --source-dir agent \
  --output-dir dist/router \
  --router-name sluice-baseline-router \
  --router-version 0.1.0 \
  --capability json-mode \
  --privacy-tier public
```

Point the miner at the manifest:

```bash
export ROUTER_MANIFEST_PATH="$(pwd)/dist/router/sluice-baseline-router-0.1.0.manifest.json"
```

## 3. Create wallets

Create coldkeys and hotkeys for the subnet owner, miner, and validator:

```bash
btcli wallet new_coldkey --wallet.name owner
btcli wallet new_coldkey --wallet.name miner
btcli wallet new_hotkey --wallet.name miner --wallet.hotkey default
btcli wallet new_coldkey --wallet.name validator
btcli wallet new_hotkey --wallet.name validator --wallet.hotkey default
```

## 4. Fund local wallets

Mint funds from the local faucet:

```bash
btcli wallet faucet --wallet.name owner --subtensor.chain_endpoint ws://127.0.0.1:9946
btcli wallet faucet --wallet.name validator --subtensor.chain_endpoint ws://127.0.0.1:9946
btcli wallet faucet --wallet.name miner --subtensor.chain_endpoint ws://127.0.0.1:9946
```

## 5. Create the subnet

```bash
btcli subnet create --wallet.name owner --subtensor.chain_endpoint ws://127.0.0.1:9946
```

Record the `netuid` you receive. The examples below use `1`.

## 6. Register the miner and validator hotkeys

Register the miner:

```bash
btcli subnets register \
  --netuid 1 \
  --wallet-name miner \
  --hotkey default \
  --network ws://127.0.0.1:9946
```

Register the validator:

```bash
btcli subnets register \
  --netuid 1 \
  --wallet-name validator \
  --hotkey default \
  --network ws://127.0.0.1:9946
```

Verify registration:

```bash
btcli subnet show --netuid 1 --network ws://127.0.0.1:9946
```

## 7. Acquire validator permit

Stake on the validator hotkey:

```bash
btcli stake add \
  --netuid 1 \
  --wallet-name validator \
  --hotkey default \
  --partial \
  --network ws://127.0.0.1:9946
```

Confirm the validator eventually shows a permit in wallet or subnet views:

```bash
btcli wallet overview --wallet.name validator --subtensor.chain_endpoint ws://127.0.0.1:9946
```

## 8. Run the nodes

Start the miner:

```bash
BT_NO_PARSE_CLI_ARGS=false python neurons/miner.py \
  --netuid 1 \
  --wallet.name miner \
  --wallet.hotkey default \
  --subtensor.chain_endpoint ws://127.0.0.1:9946
```

Start the validator in another terminal:

```bash
BT_NO_PARSE_CLI_ARGS=false python neurons/validator.py \
  --netuid 1 \
  --wallet.name validator \
  --wallet.hotkey default \
  --subtensor.chain_endpoint ws://127.0.0.1:9946
```

## 9. Enable local emissions

The subnet still needs root-network support before miner and validator emissions show up.

Register the validator on root:

```bash
btcli root register \
  --wallet.name validator \
  --wallet.hotkey default \
  --subtensor.chain_endpoint ws://127.0.0.1:9946
```

Then boost the subnet on the local root network:

```bash
btcli root boost \
  --netuid 1 \
  --increase 1 \
  --wallet.name validator \
  --wallet.hotkey default \
  --subtensor.chain_endpoint ws://127.0.0.1:9946
```

## 10. Verify emissions

Once the validator has begun setting weights and a subnet tempo has elapsed, check both roles:

```bash
btcli wallet overview --wallet.name miner --subtensor.chain_endpoint ws://127.0.0.1:9946
btcli wallet overview --wallet.name validator --subtensor.chain_endpoint ws://127.0.0.1:9946
btcli subnet show --netuid 1 --network ws://127.0.0.1:9946
```

## Troubleshooting

If the miner starts but earns nothing:

- confirm the miner hotkey is registered on the correct `netuid`
- confirm the router manifest path is valid
- confirm the validator is receiving non-empty miner manifests

If the validator starts but cannot set weights:

- confirm the validator hotkey has a permit
- confirm enough miners are serving
- confirm Docker is working if you are not in local-dev execution mode
