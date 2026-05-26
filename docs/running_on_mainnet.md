# Run on Mainnet

This guide shows the mainnet bring-up path for the Sluice subnet miner and validator.

Only use this path after you have already succeeded on [staging](running_on_staging.md) and [testnet](running_on_testnet.md). Mainnet errors are more expensive and harder to recover from.

For role expectations, see [Miner and Validator Guide](miner_validator_guide.md).

## Mainnet Safety Notes

- use separate production wallets
- do not reuse testnet passwords
- protect hotkeys and coldkeys carefully
- verify every `netuid`, wallet name, and artifact path before submitting transactions
- do not advertise router capabilities or privacy guarantees your artifact cannot actually satisfy

The exact `btcli` argument spellings can vary by release. If your installed CLI differs, prefer the form shown in `btcli --help`.

## 1. Prepare the repo

```bash
python -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
cp .env.miner.example .env.miner
cp .env.validator.example .env.validator
docker info
```

Build the router artifact you want to serve and publish it to Hugging Face.
Mainnet artifacts must use a public HTTP(S) URI, not `file://`.

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

python scripts/preflight_live.py --role both
```

## 2. Create or select wallets

Create or confirm the production wallets you will use for:

- subnet owner
- miner
- validator

Example wallet creation flow:

```bash
btcli wallet new-coldkey --wallet-name sluice_owner_main
btcli wallet new-coldkey --wallet-name sluice_miner_main
btcli wallet new-hotkey --wallet-name sluice_miner_main --hotkey miner
btcli wallet new-coldkey --wallet-name sluice_validator_main
btcli wallet new-hotkey --wallet-name sluice_validator_main --hotkey validator
```

## 3. Create the subnet

```bash
btcli subnets create \
  --wallet-name sluice_owner_main \
  --network finney \
  --subnet-name Sluice \
  --github-repo https://github.com/<your-org>/<your-repo> \
  --subnet-contact you@example.com
```

Record the resulting `netuid`.

```bash
export NETUID=<your-netuid>
export NETWORK=finney
```

## 4. Register the miner and validator hotkeys

Register the miner:

```bash
btcli subnets register \
  --netuid "${NETUID}" \
  --wallet-name sluice_miner_main \
  --hotkey miner \
  --network "${NETWORK}"
```

Register the validator:

```bash
btcli subnets register \
  --netuid "${NETUID}" \
  --wallet-name sluice_validator_main \
  --hotkey validator \
  --network "${NETWORK}"
```

Verify:

```bash
btcli subnets show --netuid "${NETUID}" --network "${NETWORK}"
```

## 5. Acquire validator permit

Stake on the validator hotkey:

```bash
btcli stake add \
  --netuid "${NETUID}" \
  --wallet-name sluice_validator_main \
  --hotkey validator \
  --network "${NETWORK}" \
  --amount <tao-to-stake>
```

Confirm the validator eventually shows a permit:

```bash
btcli wallet overview \
  --wallet-name sluice_validator_main \
  --hotkey validator \
  --netuid "${NETUID}" \
  --network "${NETWORK}"
```

## 6. Run the nodes

Start the miner:

```bash
NETUID="${NETUID}" \
SUBTENSOR_NETWORK="${NETWORK}" \
WALLET_NAME=sluice_miner_main \
WALLET_HOTKEY=miner \
AXON_PORT=8091 \
FORCE_VALIDATOR_PERMIT=1 \
ALLOW_NON_REGISTERED=0 \
MOCK=0 \
./start_miner.sh
```

Start the validator:

```bash
NETUID="${NETUID}" \
SUBTENSOR_NETWORK="${NETWORK}" \
WALLET_NAME=sluice_validator_main \
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

For long-running production setups, place both processes behind a supervisor such as `systemd`, `tmux`, or another process manager and capture logs persistently.

## 7. Start emissions for a subnet you own

If you own the subnet, check and start its emission schedule when the network allows it:

```bash
btcli subnets check-start --netuid "${NETUID}" --network "${NETWORK}"

btcli subnets start \
  --netuid "${NETUID}" \
  --wallet-name sluice_owner_main \
  --network "${NETWORK}"
```

## 8. Verify emissions and health

Check:

```bash
btcli wallet overview --wallet-name sluice_miner_main --netuid "${NETUID}" --network "${NETWORK}"
btcli wallet overview --wallet-name sluice_validator_main --netuid "${NETUID}" --network "${NETWORK}"
btcli subnets show --netuid "${NETUID}" --network "${NETWORK}"
```

Expectations:

- miner axon is reachable and consistently returns manifests
- validator logs show benchmarking and weight setting
- miner incentives and validator dividends begin changing after subnet tempo and root-network support are in place

## Production Guidelines

- pin artifacts and keep an internal record of the exact source that produced each manifest
- monitor Docker health and disk usage on validators
- restart nodes with a supervisor rather than manual shell sessions
- treat manifest version bumps as deploy events and document them
- keep fallback plans for artifact rollback if a router policy degrades
