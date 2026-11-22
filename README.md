# Seal Log

Cloud Computing Practical Works 5–6  
Mironov Egor, N4250c

Seal Log is a small SaaS prototype for recording security seals on cabinets and transport cases. Two organizations use the same application, but each organization can access only its own data.

The project uses Python, Flask, Gunicorn and SQLite. It runs in Docker on a local Linux VM. All example data and credentials are for testing.

## Documents

- [Design brief for Practical Work 5](docs/design-brief.md)
- [Completed test results](TEST_RESULTS.md)
- [Requests, responses and Docker logs](evidence/)

## Build and run

Docker must be installed and running. Execute these commands from the project folder:

```bash
docker build -t seal-log:lab .

docker volume create seal-log-data

docker run --rm \
  --mount type=volume,source=seal-log-data,target=/data \
  seal-log:lab flask --app app init-db

docker run -d \
  --name seal-log \
  -p 127.0.0.1:8000:8000 \
  --mount type=volume,source=seal-log-data,target=/data \
  seal-log:lab
```

Initialization creates the two test organizations and keeps existing records.

Check the application:

```bash
curl -i http://127.0.0.1:8000/health
```

Expected status: `200 OK`.

## Test organizations

| Organization | API token | Plan | Object limit |
|---|---|---|---:|
| Office A | demo-token-a | Basic | 5 |
| Office B | demo-token-b | Pro | 20 |

Make a request as each organization:

```bash
curl -i http://127.0.0.1:8000/me \
  -H 'Authorization: Bearer demo-token-a'

curl -i http://127.0.0.1:8000/me \
  -H 'Authorization: Bearer demo-token-b'
```

## Example workflow

Create an object as A:

```bash
curl -i http://127.0.0.1:8000/objects \
  -H 'Authorization: Bearer demo-token-a' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Cabinet A1","location":"Room A","seal_number":"A001"}'
```

Use the object ID from the response. In a fresh database, the first object has ID `1`.

Record an inspection:

```bash
curl -i http://127.0.0.1:8000/objects/1/inspections \
  -H 'Authorization: Bearer demo-token-a' \
  -H 'Content-Type: application/json' \
  -d '{"result":"intact","note":"Regular check."}'
```

Replace the seal:

```bash
curl -i http://127.0.0.1:8000/objects/1/seals \
  -H 'Authorization: Bearer demo-token-a' \
  -H 'Content-Type: application/json' \
  -d '{"seal_number":"A002"}'
```

Read the history:

```bash
curl -i http://127.0.0.1:8000/objects/1/history \
  -H 'Authorization: Bearer demo-token-a'
```

B uses the same workflow with `demo-token-b` and its own object IDs.

## API

All endpoints except `/health` require a valid token.

| Method | Path | Action |
|---|---|---|
| GET | /health | Check that the application responds |
| GET | /me | View the current organization, plan and usage |
| GET | /objects | List own objects |
| POST | /objects | Create an object with its first seal |
| GET | /objects/{id} | Read an own object and its current seal |
| POST | /objects/{id}/inspections | Record an inspection |
| POST | /objects/{id}/seals | Replace the current seal |
| GET | /objects/{id}/history | Read seal and inspection history |

Inspection results can be `intact`, `broken` or `missing`.

The server gets the tenant ID from the verified token. It checks the tenant ID when reading or changing records.

- Missing or invalid token: `401 Unauthorized`.
- Another organization's record: `404 Not Found`.
- Object limit reached: `403 Forbidden`.
- Invalid input: `400 Bad Request`.

The object count and creation are checked in one database transaction. Inspections and seal replacements do not use extra places in the allowance.

## Storage

SQLite stores its database at `/data/seal-log.db`. The `seal-log-data` Docker volume keeps the data when the application container is replaced.

## Acceptance checks

Run:

```bash
bash tests/run.sh
```

The script checks normal use, tenant isolation and the plan limit. Each check uses a separate fresh database and the same application image.

Requests, responses, build details and container logs are saved in a new folder under `evidence/`. Each folder also contains `results.md` with expected and actual results.

## Changes during implementation

The main workflow and storage model follow the design. I added `/health` and `/me` to make the application easier to check.

I also added automated acceptance checks and evidence files. The Basic plan check uses a limit of five objects and rejects the sixth creation request.

## Stop and start again

Stop the application:

```bash
docker stop seal-log
```

Start the existing container again:

```bash
docker start seal-log
```
