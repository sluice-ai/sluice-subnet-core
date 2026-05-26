# Run on Testnet

This guide shows how to register and operate the Sluice miner and validator on the Bittensor testnet.

Run [staging](running_on_staging.md) first. It is much cheaper to debug manifest, permit, and weight-setting issues on a local chain.

For role-specific guidance, see [Miner and Validator Guide](miner_validator_guide.md).

## Prerequisites

- this repository installed in a Python environment
- Docker available on validator hosts
- funded testnet wallets for subnet owner, miner, and validator
- a built router artifact and manifest for the miner

The exact `btcli` argument spellings can vary by release. If your installed CLI differs, prefer the form shown in `btcli --help`.

## 1. Prepare the repo

```bash
python -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
cp .env.miner.example .env.miner
cp .env.validator.example .env.validator
```

Install Docker on the validator host and confirm the daemon is reachable:

```bash
docker info
```

The live validator uses Docker sandboxing. Do not use `SLUICE_LOCAL_DEV_EXECUTION=1` on testnet.

## 2. Build and publish a router artifact

Build the sample router artifact and publish it to Hugging Face:

```bash
export HF_TOKEN=<write-token>

python -m sluice.router.builder \
  --source-dir agent \
  --output-dir dist/router \
  --router-name sluice-baseline-router \
  --router-version 0.1.0 \
  --capability json-mode \
  --privacy-tier public \
  --hf-repo-id <huggingface-user-or-org>/<repo-name> \
  --hf-repo-type model \
  --hf-path-prefix routers
```

The builder uploads `dist/router/sluice-baseline-router-0.1.0.tar.gz`,
rewrites the manifest's `artifact_uri` to a Hugging Face `resolve` URL, and
uploads the manifest beside the tarball. Do not announce a `file://` artifact
URI on testnet or mainnet. It only works for local smoke tests.

Write production env files:

```bash
cat > .env.miner <<EOF
ROUTER_MANIFEST_PATH=$(pwd)/dist/router/sluice-baseline-router-0.1.0.manifest.json
ROUTER_LABEL=sluice-baseline-router
ROUTER_VERSION=0.1.0
ROUTER_SUMMARY=Baseline Sluice router artifact.
ROUTER_SUPPORTED_CAPABILITIES=json-mode
ROUTER_SUPPORTED_PRIVACY_TIERS=public
SLUICE_ALLOW_LOCAL_ARTIFACT=0
EOF

cat > .env.validator <<EOF
SLUICE_TASK_API=
SLUICE_SKIP_SANDBOX_BUILD=0
SLUICE_SANDBOX_IMAGE=sluice-router-agent:latest
SLUICE_ARTIFACT_CACHE_DIR=$HOME/.cache/sluice/router-artifacts
MAX_CONCURRENT_SANDBOXES=4
SANDBOX_TIMEOUT=45
SLUICE_LOCAL_DEV_EXECUTION=0
HF_TOKEN=
HF_ENDPOINT=
SLUICE_MOCK_ROUTER_MANIFEST_PATH=
EOF
```

Run the live preflight. This must pass before live operation:

```bash
python scripts/preflight_live.py --role both
```

## 3. Create wallets

```bash
btcli wallet new-coldkey --wallet-name sluice_owner_test
btcli wallet new-coldkey --wallet-name sluice_miner_test
btcli wallet new-hotkey --wallet-name sluice_miner_test --hotkey miner
btcli wallet new-coldkey --wallet-name sluice_validator_test
btcli wallet new-hotkey --wallet-name sluice_validator_test --hotkey validator
```

Fund them with testnet TAO using the currently supported community path.

Verify balances:

```bash
btcli wallet balance --wallet-name sluice_owner_test --network test
btcli wallet balance --wallet-name sluice_miner_test --network test
btcli wallet balance --wallet-name sluice_validator_test --network test
```

## 4. Create the subnet

Skip this step if you are joining an existing Sluice testnet subnet.

```bash
btcli subnets create \
  --wallet-name sluice_owner_test \
  --network test \
  --subnet-name Sluice \
  --github-repo https://github.com/<your-org>/<your-repo> \
  --subnet-contact you@example.com
```

Record the `netuid`.

Set it for the remaining commands:

```bash
export NETUID=<your-netuid>
export NETWORK=test
```

## 5. Register miner and validator hotkeys

Register the miner:

```bash
btcli subnets register \
  --netuid "${NETUID}" \
  --wallet-name sluice_miner_test \
  --hotkey miner \
  --network "${NETWORK}"
```

Register the validator:

```bash
btcli subnets register \
  --netuid "${NETUID}" \
  --wallet-name sluice_validator_test \
  --hotkey validator \
  --network "${NETWORK}"
```

Verify:

```bash
btcli subnets show --netuid "${NETUID}" --network "${NETWORK}"
```

## 6. Acquire validator permit

Stake on the validator hotkey:

```bash
btcli stake add \
  --netuid "${NETUID}" \
  --wallet-name sluice_validator_test \
  --hotkey validator \
  --network "${NETWORK}" \
  --amount <tao-to-stake>
```

Then confirm the validator eventually shows a permit:

```bash
btcli wallet overview \
  --wallet-name sluice_validator_test \
  --hotkey validator \
  --netuid "${NETUID}" \
  --network "${NETWORK}"
```

## 7. Start emissions for a subnet you own

If you created the subnet, check and start its emission schedule when the network allows it:

```bash
btcli subnets check-start --netuid "${NETUID}" --network "${NETWORK}"

btcli subnets start \
  --netuid "${NETUID}" \
  --wallet-name sluice_owner_test \
  --network "${NETWORK}"
```

## 8. Run the miner and validator

Start the miner:

```bash
NETUID="${NETUID}" \
SUBTENSOR_NETWORK="${NETWORK}" \
WALLET_NAME=sluice_miner_test \
WALLET_HOTKEY=miner \
AXON_PORT=8091 \
FORCE_VALIDATOR_PERMIT=1 \
ALLOW_NON_REGISTERED=0 \
MOCK=0 \
./start_miner.sh
```

Start the validator in another terminal:

```bash
NETUID="${NETUID}" \
SUBTENSOR_NETWORK="${NETWORK}" \
WALLET_NAME=sluice_validator_test \
WALLET_HOTKEY=validator \
AXON_PORT=8092 \
MOCK=0 \
AXON_OFF=0 \
DISABLE_SET_WEIGHTS=0 \
SAMPLE_SIZE=50 \
CHALLENGE_INTERVAL=12 \
EPOCH_LENGTH=100 \
./start_validator.sh
```

## 9. Verify health

Check miner and validator state:

```bash
btcli wallet overview --wallet-name sluice_miner_test --netuid "${NETUID}" --network "${NETWORK}"
btcli wallet overview --wallet-name sluice_validator_test --netuid "${NETUID}" --network "${NETWORK}"
btcli subnets show --netuid "${NETUID}" --network "${NETWORK}"
```

Signs of a good setup:

- miner hotkey is active on the target subnet
- validator eventually shows a permit
- validator logs show task sampling, rewards, and weight updates
- miner and validator emissions stop being stuck at zero after root-network support and subnet tempo progression
