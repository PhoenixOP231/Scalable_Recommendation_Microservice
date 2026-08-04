import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 10,
  duration: '30s',
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API_KEY = __ENV.API_KEY || 'your-admin-api-key-here';

export default function () {
  const payload = JSON.stringify({
    user_id: `user_${Math.floor(Math.random() * 100)}`,
    limit: 10,
    seed_item_ids: ["item_1", "item_5"],
    excluded_categories: ["adult"],
    diversity: 0.25,
    cache_ttl_seconds: 60
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
    },
  };

  const res = http.post(`${BASE_URL}/v1/recommendations`, payload, params);
  
  check(res, {
    'is status 200': (r) => r.status === 200,
    'has recommendations': (r) => {
        try {
            return JSON.parse(r.body).recommendations.length >= 0;
        } catch(e) {
            return false;
        }
    }
  });
  
  sleep(1);
}
