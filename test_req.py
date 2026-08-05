import requests

print("Creating interaction...")
res = requests.post("https://scalable-recommendation-api.vercel.app/v1/demo/interactions", json={
    "user_id": "demo-user",
    "item_id": "item_1",
    "interaction_type": "view"
})
print("Interaction:", res.status_code, res.text)

print("\nFetching recommendations...")
res = requests.post("https://scalable-recommendation-api.vercel.app/v1/demo/recommendations", json={
    "user_id": "demo-user",
    "limit": 4
}, cookies=res.cookies)
print("Recommendations:", res.status_code, res.text)
