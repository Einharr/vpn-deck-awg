FROM ghcr.io/steamdeckhomebrew/holo-base:latest

ARG AMNEZIAWG_GO_REF=v3.0.3
ARG AMNEZIAWG_TOOLS_REF=v3.0.20260730

RUN pacman -Sy --noconfirm && \
    pacman -S --noconfirm go git base-devel libmnl python && \
    pacman -Scc --noconfirm

RUN git clone --depth 1 --branch "${AMNEZIAWG_GO_REF}" \
      https://github.com/amnezia-vpn/amneziawg-go.git /tmp/amneziawg-go && \
    make -C /tmp/amneziawg-go

RUN git clone --depth 1 --branch "${AMNEZIAWG_TOOLS_REF}" \
      https://github.com/amnezia-vpn/amneziawg-tools.git /tmp/amneziawg-tools && \
    make -C /tmp/amneziawg-tools/src

COPY infra/patch-awg-quick.py /tmp/patch-awg-quick.py

RUN mkdir -p /binaries && \
    cp /tmp/amneziawg-go/amneziawg-go /binaries/amneziawg-go && \
    cp /tmp/amneziawg-tools/src/wg /binaries/awg && \
    cp /tmp/amneziawg-tools/src/wg-quick/linux.bash /binaries/awg-quick && \
    python /tmp/patch-awg-quick.py /binaries/awg-quick && \
    chmod 0755 /binaries/amneziawg-go /binaries/awg /binaries/awg-quick && \
    printf '{\n  "amneziawg-go": "%s",\n  "awg": "%s",\n  "awg-quick": "%s"\n}\n' \
      "${AMNEZIAWG_GO_REF}" "${AMNEZIAWG_TOOLS_REF}" "${AMNEZIAWG_TOOLS_REF}" \
      > /binaries/versions.json
