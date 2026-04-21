module.exports = {
  apps: [
    {
      name: "CryptoPlatform",
      script: ".next/standalone/server.js",
      env: {
        PORT: 33441,
        NODE_ENV: "production"
      }
    }
  ]
}
