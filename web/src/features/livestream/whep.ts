export type WhepSession = { close: () => void }

function waitForIceGathering(pc: RTCPeerConnection, timeoutMs: number): Promise<void> {
  if (pc.iceGatheringState === 'complete') return Promise.resolve()
  return new Promise((resolve) => {
    const done = () => {
      pc.removeEventListener('icegatheringstatechange', onChange)
      resolve()
    }
    const onChange = () => pc.iceGatheringState === 'complete' && done()
    pc.addEventListener('icegatheringstatechange', onChange)
    setTimeout(done, timeoutMs)
  })
}

export async function startWhep(
  url: string,
  video: HTMLVideoElement,
  onState: (state: RTCPeerConnectionState) => void,
): Promise<WhepSession> {
  const pc = new RTCPeerConnection()
  let resourceUrl: string | null = null

  pc.addTransceiver('video', { direction: 'recvonly' })
  pc.addTransceiver('audio', { direction: 'recvonly' })
  pc.ontrack = (e) => {
    if (e.streams[0] && video.srcObject !== e.streams[0]) video.srcObject = e.streams[0]
  }
  pc.onconnectionstatechange = () => onState(pc.connectionState)

  const close = () => {
    pc.close()
    video.srcObject = null
    if (resourceUrl) fetch(resourceUrl, { method: 'DELETE' }).catch(() => undefined)
  }

  try {
    await pc.setLocalDescription(await pc.createOffer())
    await waitForIceGathering(pc, 2000)

    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/sdp' },
      body: pc.localDescription!.sdp,
    })
    if (!res.ok) throw new Error(`WHEP endpoint returned ${res.status}`)

    const location = res.headers.get('Location')
    if (location) resourceUrl = new URL(location, url).toString()
    await pc.setRemoteDescription({ type: 'answer', sdp: await res.text() })
  } catch (err) {
    close()
    throw err
  }

  return { close }
}
