import express from 'express'
import { betterAuth } from 'better-auth'
import { organization } from 'better-auth/plugins'
import Database from 'better-sqlite3'

const db = new Database(process.env.DATABASE_URL?.replace('file:', '') || './auth.db')

export const auth = betterAuth({
  database: db,
  secret: process.env.BETTER_AUTH_SECRET || 'super-secret-dev-key-at-least-32-chars',
  baseURL: process.env.BETTER_AUTH_URL || 'http://localhost:3000',
  plugins: [organization()],
  emailAndPassword: {
    enabled: true,
    requireEmailVerification: false,
  },
  trustedOrigins: [
    'http://localhost:5173',
    'http://localhost:8000',
    'http://localhost:3000',
  ],
})

const app = express()
app.use(express.json())

// Mount Better Auth handler at /api/auth
app.all('/api/auth/*', async (req, res) => {
  const response = await auth.handler(
    new Request(`http://${req.headers.host}${req.url}`, {
      method: req.method,
      headers: req.headers as HeadersInit,
      body: req.method !== 'GET' && req.method !== 'HEAD'
        ? JSON.stringify(req.body)
        : undefined,
    })
  )

  res.status(response.status)
  response.headers.forEach((value, key) => res.setHeader(key, value))
  const body = await response.text()
  res.send(body)
})

app.get('/health', (_req, res) => res.json({ status: 'ok' }))

const PORT = process.env.PORT || 3000
app.listen(PORT, () => console.log(`Auth sidecar running on port ${PORT}`))
