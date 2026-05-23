# Miner and Validator Guide

This guide is for people operating Sluice subnet nodes.

## Roles

Miner responsibilities:

- build and publish a pinned router artifact
- announce a valid manifest over the subnet
- keep the manifest honest about capabilities and privacy tiers
- stay online so validators can query the miner axon

Validator responsibilities:

- fetch benchmark tasks
- query miners for manifests
- verify artifact digests
- sandbox router execution
- score miner outputs and set subnet weights

## Before You Register

- Install Python and the project dependencies from `requirements.txt`
- Install Docker on validator machines
- Create separate wallets or hotkeys for miner and validator roles
- Decide which network you are targeting: local chain, testnet, or mainnet
- Build or obtain a router artifact and manifest before starting a miner

## Miner Checklist

1. Build a router artifact and manifest.
2. Upload the artifact to a public HTTP(S) URI before running on testnet or mainnet.
3. Put the manifest path in `.env.miner` or export `ROUTER_MANIFEST_PATH`.
4. Confirm the manifest entrypoint and digest are correct.
5. Register the miner hotkey on the subnet.
6. Start the miner and confirm the axon is serving.

Recommended miner guidelines:

- Only advertise artifacts you can reproduce and redeploy.
- Do not use `file://` artifact URIs outside local smoke tests.
- Keep the manifest description, version, and supported capabilities accurate.
- Test the artifact with `python scripts/smoke_subnet_flow.py` before going on-chain.
- Avoid overstating privacy support or capabilities; validators will score the actual output, not the claim.

## Validator Checklist

1. Configure `.env.validator`.
2. Make sure Docker works on the host.
3. Register the validator hotkey on the subnet.
4. Stake enough to obtain a validator permit on the target subnet.
5. Start the validator and confirm it is sampling tasks and updating scores.
6. If you own the subnet, start its emission schedule when the network allows it.

Recommended validator guidelines:

- Use a machine with reliable disk, CPU, and Docker support.
- Watch `SLUICE_ARTIFACT_CACHE_DIR` growth and rotate or clean if needed.
- Keep benchmark task sources and scoring logic deterministic.
- Do not mix serving-layer API credentials into validator benchmarking unless the code path explicitly requires them.

## Registration Flow

The exact `btcli` flag spellings can vary by release. If your installed CLI uses slightly different names, prefer the forms shown by `btcli --help`.

High-level order:

1. Create or fund the wallet that will own or participate in the subnet.
2. Register the subnet if you are the subnet owner.
3. Register the miner hotkey on the subnet.
4. Register the validator hotkey on the subnet.
5. Stake enough on the validator hotkey to acquire a validator permit.
6. Start both nodes.
7. If you own the subnet, start its emission schedule so miner incentives and validator dividends can begin flowing.

## Runtime Timing Knobs

The helper scripts are configured by environment variables so operators can tune cadence without editing code.

Validator script knobs:

- `MOCK`: run against the local mock network. Default is `0`.
- `AXON_OFF`: do not serve the validator axon. Default is `0`.
- `CHALLENGE_INTERVAL`: seconds between challenge rounds. Default is `12`.
- `SAMPLE_SIZE`: miners queried per challenge round. Default is `50`.
- `NUM_CONCURRENT_FORWARDS`: challenge rounds run concurrently. Default is `1`.
- `TIMEOUT`: dendrite query timeout in seconds. Default is `10`.
- `EPOCH_LENGTH`: block interval used for metagraph sync and weight-setting attempts. Default is `100`.
- `DISABLE_SET_WEIGHTS=1`: keeps the validator scoring miners without emitting weights.

Miner script knobs:

- `MOCK`: run against the local mock network. Default is `0`.
- `FORCE_VALIDATOR_PERMIT`: require callers to have a validator permit once permits exist. Default is `1`.
- `ALLOW_NON_REGISTERED`: accept unregistered callers. Default is `0`.
- `EPOCH_LENGTH`: block interval used for miner metagraph sync. Default is `100`.

For emissions, keep `DISABLE_SET_WEIGHTS` unset or `0`, make sure the validator has a permit, and make sure the subnet emission schedule has started.

Before live operation, run:

```bash
python scripts/preflight_live.py --role both
```

## Verifying That Things Work

Signs the miner is healthy:

- the process starts without registration errors
- the axon is serving
- validators receive `router_manifest_json` responses

Signs the validator is healthy:

- the validator fetches tasks and samples miner UIDs
- rewards are non-zero for at least some miners
- the validator begins setting weights after enough blocks

Useful checks:

- `btcli wallet overview ...`
- `btcli subnet show --netuid <netuid> ...`
- miner and validator logs

## Common Failure Modes

`Unregistered neuron`

- the hotkey is not registered on the subnet you are targeting

`NeuronNoValidatorPermit`

- the validator does not yet have a permit; add stake and wait for the subnet to update

`WeightVecLengthIsLow`

- the validator tried to set weights with too few valid miner responses; check miner availability and sandbox failures

`Zero emissions despite healthy nodes`

- the validator may be running correctly, but the subnet emission schedule may not be started yet
