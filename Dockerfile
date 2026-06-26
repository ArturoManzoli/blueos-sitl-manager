# syntax=docker/dockerfile:1

# ---- Frontend build ----
FROM node:20-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package.json frontend/yarn.lock* ./
RUN yarn install --frozen-lockfile || yarn install
COPY frontend/ ./
RUN yarn build

# ---- Runtime ----
FROM python:3.11-slim AS runtime
WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend-builder /frontend/dist ./static

EXPOSE 80

LABEL version="0.1.0"

# Map container port 80 to a free host port and bridge to the vehicle network so the
# extension can reach BlueOS services via host.docker.internal.
LABEL permissions='{\
  "ExposedPorts": {\
    "80/tcp": {}\
  },\
  "HostConfig": {\
    "ExtraHosts": ["host.docker.internal:host-gateway"],\
    "PortBindings": {\
      "80/tcp": [\
        {\
          "HostPort": ""\
        }\
      ]\
    },\
    "Memory": 104857600\
  }\
}'

LABEL authors='[\
  {\
    "name": "BlueOS Community",\
    "email": "support@example.com"\
  }\
]'

LABEL company='{\
  "about": "Community-maintained BlueOS extension for SITL development.",\
  "name": "BlueOS Community",\
  "email": "support@example.com"\
}'

LABEL type="tool"
LABEL tags='[\
  "simulation",\
  "development",\
  "navigation"\
]'
LABEL readme="https://raw.githubusercontent.com/BlueOS-Community/blueos-sitl-manager/{tag}/README.md"
LABEL links='{\
  "github": "https://github.com/BlueOS-Community/blueos-sitl-manager",\
  "support": "https://github.com/BlueOS-Community/blueos-sitl-manager/issues"\
}'
LABEL requirements="core >= 1.1"

CMD ["python", "main.py"]
