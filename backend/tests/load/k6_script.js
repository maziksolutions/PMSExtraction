/**
 * k6 Load Test Script — Maritime PMS Data Extraction Tool
 *
 * Test flow: login → list vessels → list components → list jobs → list spares
 *
 * Stages:
 *   - Ramp up 0 → 50 users over 2 minutes
 *   - Hold 50 users for 5 minutes
 *   - Ramp down to 0 over 1 minute
 *
 * Thresholds:
 *   - p95 response time < 2000ms
 *   - Error rate < 1%
 *
 * Run: k6 run --config k6_config.json k6_script.js
 */

import http from 'k6/http'
import { check, sleep, group } from 'k6'
import { Rate, Trend } from 'k6/metrics'

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000'
const TEST_EMAIL = __ENV.TEST_EMAIL || 'admin@maritime.test'
const TEST_PASSWORD = __ENV.TEST_PASSWORD || 'testpassword123'

// ---------------------------------------------------------------------------
// Custom metrics
// ---------------------------------------------------------------------------

const errorRate = new Rate('errors')
const loginDuration = new Trend('login_duration')
const listVesselsDuration = new Trend('list_vessels_duration')
const listComponentsDuration = new Trend('list_components_duration')
const listJobsDuration = new Trend('list_jobs_duration')
const listSparesDuration = new Trend('list_spares_duration')

// ---------------------------------------------------------------------------
// Thresholds
// ---------------------------------------------------------------------------

export const options = {
  stages: [
    { duration: '2m', target: 50 },   // Ramp up to 50 users
    { duration: '5m', target: 50 },   // Hold at 50 users
    { duration: '1m', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'],  // 95% of requests must complete < 2s
    errors: ['rate<0.01'],              // Error rate must be < 1%
    login_duration: ['p(95)<3000'],
    list_vessels_duration: ['p(95)<1500'],
    list_components_duration: ['p(95)<2000'],
    list_jobs_duration: ['p(95)<2000'],
    list_spares_duration: ['p(95)<2000'],
  },
}

// ---------------------------------------------------------------------------
// Main virtual user function
// ---------------------------------------------------------------------------

export default function () {
  let accessToken = ''
  let vesselId = ''

  // Step 1: Login
  group('login', function () {
    const loginRes = http.post(
      `${BASE_URL}/api/v1/auth/login`,
      JSON.stringify({ email: TEST_EMAIL, password: TEST_PASSWORD }),
      { headers: { 'Content-Type': 'application/json' } }
    )

    loginDuration.add(loginRes.timings.duration)

    const ok = check(loginRes, {
      'login status 200': (r) => r.status === 200,
      'login returns token': (r) => {
        try {
          return JSON.parse(r.body).access_token !== undefined
        } catch {
          return false
        }
      },
    })

    if (!ok) {
      errorRate.add(1)
      return
    }

    errorRate.add(0)
    accessToken = JSON.parse(loginRes.body).access_token
  })

  if (!accessToken) {
    sleep(1)
    return
  }

  const authHeaders = {
    Authorization: `Bearer ${accessToken}`,
    'Content-Type': 'application/json',
  }

  sleep(0.5)

  // Step 2: List vessels
  group('list_vessels', function () {
    const res = http.get(`${BASE_URL}/api/v1/vessels`, { headers: authHeaders })

    listVesselsDuration.add(res.timings.duration)

    const ok = check(res, {
      'list vessels 200': (r) => r.status === 200,
    })
    errorRate.add(ok ? 0 : 1)

    try {
      const data = JSON.parse(res.body)
      if (data.items && data.items.length > 0) {
        vesselId = data.items[0].id
      }
    } catch {
      // no vessels
    }
  })

  if (!vesselId) {
    sleep(1)
    return
  }

  sleep(0.5)

  // Step 3: List components
  group('list_components', function () {
    const res = http.get(`${BASE_URL}/api/v1/vessels/${vesselId}/components`, {
      headers: authHeaders,
    })

    listComponentsDuration.add(res.timings.duration)

    const ok = check(res, {
      'list components 200': (r) => r.status === 200,
    })
    errorRate.add(ok ? 0 : 1)
  })

  sleep(0.5)

  // Step 4: List jobs
  group('list_jobs', function () {
    const res = http.get(`${BASE_URL}/api/v1/vessels/${vesselId}/jobs`, {
      headers: authHeaders,
    })

    listJobsDuration.add(res.timings.duration)

    const ok = check(res, {
      'list jobs 200': (r) => r.status === 200,
    })
    errorRate.add(ok ? 0 : 1)
  })

  sleep(0.5)

  // Step 5: List spares
  group('list_spares', function () {
    const res = http.get(`${BASE_URL}/api/v1/vessels/${vesselId}/spares`, {
      headers: authHeaders,
    })

    listSparesDuration.add(res.timings.duration)

    const ok = check(res, {
      'list spares 200': (r) => r.status === 200,
    })
    errorRate.add(ok ? 0 : 1)
  })

  sleep(1)
}
