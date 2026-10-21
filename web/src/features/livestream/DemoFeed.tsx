import { useEffect, useRef } from 'react'

const W = 1280
const H = 720

function seeded(seed: number) {
  return () => {
    seed = (seed * 16807) % 2147483647
    return seed / 2147483647
  }
}

const rand = seeded(42)
const WORLD = 2400
const trees = Array.from({ length: 70 }, () => ({
  x: rand() * WORLD,
  y: rand() * H,
  r: 14 + rand() * 34,
}))

function fenceY(worldX: number) {
  return H * 0.58 + Math.sin(worldX / 260) * 38 + Math.sin(worldX / 90) * 6
}

/** Simulated aerial perimeter feed, used when no drone stream is configured. */
export function DemoFeed({ onReady }: { onReady?: () => void }) {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return
    onReady?.()

    let raf = 0
    const start = performance.now()

    const draw = (now: number) => {
      const t = (now - start) / 1000
      const pan = (t * 28) % WORLD

      const g = ctx.createLinearGradient(0, 0, 0, H)
      g.addColorStop(0, '#16231f')
      g.addColorStop(1, '#0c1513')
      ctx.fillStyle = g
      ctx.fillRect(0, 0, W, H)

      ctx.fillStyle = 'rgba(180, 170, 140, 0.10)'
      ctx.beginPath()
      ctx.moveTo(0, H * 0.78)
      for (let x = 0; x <= W; x += 40) ctx.lineTo(x, H * 0.78 + Math.sin((x + pan) / 300) * 20)
      ctx.lineTo(W, H * 0.9)
      for (let x = W; x >= 0; x -= 40) ctx.lineTo(x, H * 0.88 + Math.sin((x + pan) / 300) * 20)
      ctx.closePath()
      ctx.fill()

      for (const tree of trees) {
        const x = ((tree.x - pan) % WORLD + WORLD) % WORLD - 200
        if (x < -80 || x > W + 80) continue
        ctx.fillStyle = 'rgba(30, 60, 42, 0.9)'
        ctx.beginPath()
        ctx.arc(x, tree.y, tree.r, 0, Math.PI * 2)
        ctx.fill()
        ctx.fillStyle = 'rgba(70, 110, 80, 0.25)'
        ctx.beginPath()
        ctx.arc(x - tree.r * 0.3, tree.y - tree.r * 0.3, tree.r * 0.55, 0, Math.PI * 2)
        ctx.fill()
      }

      ctx.strokeStyle = 'rgba(200, 210, 200, 0.55)'
      ctx.lineWidth = 2
      ctx.setLineDash([6, 5])
      ctx.beginPath()
      for (let x = 0; x <= W; x += 8) {
        const y = fenceY(x + pan)
        if (x === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      }
      ctx.stroke()
      ctx.setLineDash([])
      ctx.fillStyle = 'rgba(220, 225, 220, 0.7)'
      const postStep = 60
      for (let wx = Math.floor(pan / postStep) * postStep; wx < pan + W; wx += postStep) {
        const x = wx - pan
        ctx.fillRect(x - 2, fenceY(wx) - 2, 4, 4)
      }

      const cycle = t % 14
      if (cycle > 4 && cycle < 11) {
        const p = (cycle - 4) / 7
        const px = W * (0.25 + p * 0.45)
        const py = fenceY(px + pan) - 60 + Math.sin(p * 9) * 6
        ctx.fillStyle = 'rgba(240, 235, 220, 0.85)'
        ctx.beginPath()
        ctx.ellipse(px, py, 7, 10, 0, 0, Math.PI * 2)
        ctx.fill()

        const bw = 64
        const bh = 74
        ctx.strokeStyle = '#fb7185'
        ctx.lineWidth = 2
        ctx.strokeRect(px - bw / 2, py - bh / 2, bw, bh)
        ctx.fillStyle = '#fb7185'
        ctx.fillRect(px - bw / 2, py - bh / 2 - 22, 118, 22)
        ctx.fillStyle = '#0b0f14'
        ctx.font = '600 14px ui-monospace, monospace'
        ctx.fillText(`person ${(0.82 + Math.sin(t) * 0.05).toFixed(2)}`, px - bw / 2 + 6, py - bh / 2 - 6)
      }

      for (let i = 0; i < 900; i++) {
        ctx.fillStyle = `rgba(255,255,255,${Math.random() * 0.05})`
        ctx.fillRect(Math.random() * W, Math.random() * H, 2, 2)
      }
      ctx.fillStyle = 'rgba(0,0,0,0.12)'
      for (let y = 0; y < H; y += 3) ctx.fillRect(0, y, W, 1)

      const vignette = ctx.createRadialGradient(W / 2, H / 2, H * 0.35, W / 2, H / 2, H * 0.95)
      vignette.addColorStop(0, 'rgba(0,0,0,0)')
      vignette.addColorStop(1, 'rgba(0,0,0,0.55)')
      ctx.fillStyle = vignette
      ctx.fillRect(0, 0, W, H)

      raf = requestAnimationFrame(draw)
    }

    raf = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(raf)
  }, [onReady])

  return <canvas ref={ref} width={W} height={H} className="h-full w-full object-cover" />
}
