// ga_worker.js — Unthrottled Background Timer for GA Heartbeat
// Modern browsers sleep background tabs but Web Workers run unthrottled.

let timerId = null;

self.onmessage = function(event) {
    if (event.data === 'start') {
        if (timerId) clearInterval(timerId);
        
        // Trigger heartbeat immediately upon start
        self.postMessage('ping');
        
        // Send heartbeat ping every 15 seconds
        timerId = setInterval(() => {
            self.postMessage('ping');
        }, 15000);
    } else if (event.data === 'stop') {
        if (timerId) {
            clearInterval(timerId);
            timerId = null;
        }
    }
};
