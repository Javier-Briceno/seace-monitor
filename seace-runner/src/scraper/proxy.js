// import net from "net";
// import http from "http";

// /**
//  * HTTP CONNECT proxy server.
//  *
//  * Why this works:
//  * - Chromium's internal network stack bypasses the VPN routing table
//  * - Node's net module correctly routes through the VPN (like curl does)
//  * - Chromium connects to this local proxy, which resolves DNS and
//  *   forwards traffic using Node's net module → goes through VPN → SEACE
//  *
//  * Chromium supports HTTP CONNECT via --proxy-server=http://127.0.0.1:1080
//  */
// export function startLocalProxy(port = 1080) {
//   return new Promise((resolve, reject) => {
//     const server = http.createServer((req, res) => {
//       res.writeHead(405, { "Content-Type": "text/plain" });
//       res.end("Only CONNECT method is supported");
//     });

//     server.on("connect", (req, clientSocket, head) => {
//       const [host, portStr] = req.url.split(":");
//       const targetPort = parseInt(portStr) || 443;

//       const targetSocket = net.createConnection(targetPort, host, () => {
//         clientSocket.write("HTTP/1.1 200 Connection Established\r\n\r\n");
//         if (head && head.length > 0) targetSocket.write(head);
//         targetSocket.pipe(clientSocket);
//         clientSocket.pipe(targetSocket);
//       });

//       targetSocket.on("error", (err) => {
//         console.error(`[proxy] → ${host}:${targetPort} failed: ${err.message}`);
//         clientSocket.write("HTTP/1.1 502 Bad Gateway\r\n\r\n");
//         clientSocket.destroy();
//       });

//       clientSocket.on("error", () => targetSocket.destroy());
//       targetSocket.on("close", () => clientSocket.destroy());
//       clientSocket.on("close", () => targetSocket.destroy());
//     });

//     server.on("error", reject);

//     server.listen(port, "127.0.0.1", () => {
//       console.log(`[proxy] HTTP CONNECT proxy listening on 127.0.0.1:${port}`);
//       resolve(server);
//     });
//   });
// }

// export function stopLocalProxy(server) {
//   return new Promise((resolve) => {
//     if (!server) return resolve();
//     server.close(() => {
//       console.log("[proxy] HTTP CONNECT proxy stopped");
//       resolve();
//     });
//   });
// }