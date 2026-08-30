FROM ghcr.io/steamdeckhomebrew/holo-base:latest

# AWG 3.1 userspace runtime. The current go tag is newer than the tools tag;
# this pair is also used by the current standalone AmneziaWG clients.
ARG AMNEZIAWG_GO_REF=v3.1.20260814
ARG AMNEZIAWG_TOOLS_REF=v3.1.20260812

RUN pacman -Sy --noconfirm && \
    pacman -S --noconfirm go git base-devel libmnl python && \
    pacman -Scc --noconfirm

RUN git clone --depth 1 --branch "${AMNEZIAWG_GO_REF}" \
      https://github.com/amnezia-vpn/amneziawg-go.git /tmp/amneziawg-go && \
    make -C /tmp/amneziawg-go

RUN git clone --depth 1 --branch "${AMNEZIAWG_TOOLS_REF}" \
      https://github.com/amnezia-vpn/amneziawg-tools.git /tmp/amneziawg-tools && \
    # Upstream config.c currently rejects a syntactically valid empty I1-I5
    # line because get_value() requires at least one byte after '='. Native
    # Amnezia exports can contain e.g. `I2 =`, so preserve the config and fix
    # the parser rather than deleting user parameters.
    sed -i 's/if (keylen >= linelen)/if (keylen > linelen)/' /tmp/amneziawg-tools/src/config.c && \
    grep -q 'if (keylen > linelen)' /tmp/amneziawg-tools/src/config.c && \
    make -C /tmp/amneziawg-tools/src && \
    printf '[Interface]\nI1 =\nI2 =\nI3 =\nI4 =\nI5 =\n' > /tmp/empty-i.conf && \
    ( /tmp/amneziawg-tools/src/wg setconf vpn-deck-parser-test /tmp/empty-i.conf 2>&1 || true ) > /tmp/empty-i.out && \
    ! grep -q 'Line unrecognized' /tmp/empty-i.out

COPY infra/patch-awg-quick.py /tmp/patch-awg-quick.py

RUN mkdir -p /binaries && \
    cp /tmp/amneziawg-go/amneziawg-go /binaries/amneziawg-go && \
    cp /tmp/amneziawg-tools/src/wg /binaries/awg && \
    cp /tmp/amneziawg-tools/src/wg-quick/linux.bash /binaries/awg-quick && \
    python /tmp/patch-awg-quick.py /binaries/awg-quick && \
    chmod 0755 /binaries/amneziawg-go /binaries/awg /binaries/awg-quick && \
    printf '{\n  "amneziawg-go": "%s",\n  "awg": "%s",\n  "awg-quick": "%s",\n  "patches": ["allow-empty-I1-I5"]\n}\n' \
      "${AMNEZIAWG_GO_REF}" "${AMNEZIAWG_TOOLS_REF}" "${AMNEZIAWG_TOOLS_REF}" \
      > /binaries/versions.json
