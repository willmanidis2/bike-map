# Citibike Heatmap

See every Citibike ride you've ever taken. Upload your ride receipt emails and get a beautiful heatmap visualization.

**100% private** — your emails are processed entirely in your browser. Nothing is uploaded to any server.

## How it works

1. Export your Citibike ride receipt emails as .eml files (instructions included in the app)
2. Upload them to the site
3. See your personal ride heatmap

## Tech

- Static site — no backend, no database
- Email parsing via [postal-mime](https://github.com/postalsys/postal-mime) (client-side)
- Route polylines extracted from Citibike's static map URLs embedded in receipt emails
- [MapLibre GL JS](https://maplibre.org/) with CARTO dark basemap
- OSRM cycling router fallback for rides without email polylines

## Deploy

Push to GitHub and connect to Vercel, or:

```
npx vercel
```
