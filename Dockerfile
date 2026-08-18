# syntax=docker/dockerfile:1

# ---- Frontend build ----
# Runs on the build machine's own architecture rather than the target's, since this stage only
# produces static files: no emulation when cross-building the arm images, and no need for a
# toolchain that exists for every target. Debian rather than Alpine because lightningcss (via
# Tailwind) ships no prebuilt binary for 32-bit ARM on musl, which is what a Pi running the
# armhf userspace would land on.
FROM --platform=$BUILDPLATFORM node:20-bookworm-slim AS frontend-builder
WORKDIR /frontend
COPY frontend/package.json frontend/yarn.lock* ./
# Strict: a lockfile that does not match package.json should fail the build rather than quietly
# resolve a different dependency tree than the one that was tested.
RUN yarn install --frozen-lockfile
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

# User-saved and imported presets live here, bind-mounted below so they survive updates.
ENV SITL_CUSTOM_PRESETS_DIR=/app/persistent/custom_presets
ENV SITL_CUSTOM_LOCATIONS_DIR=/app/persistent/custom_locations
ENV SITL_CUSTOM_ENVIRONMENTS_DIR=/app/persistent/custom_environments

LABEL version="0.2.1"

# Map container port 80 to a free host port and bridge to the vehicle network so the
# extension can reach BlueOS services via host.docker.internal. The Binds entry persists
# user-saved presets on the host across extension updates.
LABEL permissions='{\
  "ExposedPorts": {\
    "80/tcp": {}\
  },\
  "HostConfig": {\
    "Binds": ["/usr/blueos/extensions/sitl-manager:/app/persistent"],\
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
    "name": "Arturo Manzoli",\
    "email": "arturomanzoli@gmail.com"\
  }\
]'

LABEL company='{\
  "about": "",\
  "name": "Blue Robotics",\
  "email": "support@bluerobotics.com"\
}'

LABEL type="tool"
LABEL tags='[\
  "simulation",\
  "development",\
  "navigation"\
]'
LABEL readme="https://raw.githubusercontent.com/ArturoManzoli/blueos-sitl-manager/{tag}/README.md"
LABEL links='{\
  "github": "https://github.com/ArturoManzoli/blueos-sitl-manager",\
  "support": "https://github.com/ArturoManzoli/blueos-sitl-manager/issues"\
}'
LABEL requirements="core >= 1.1"

CMD ["python", "main.py"]
