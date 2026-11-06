function formatForMySQLWithMillis(date) {
    const pad = (n, width = 2) => String(n).padStart(width, '0');

    const year = date.getFullYear();
    const month = pad(date.getMonth() + 1);
    const day = pad(date.getDate());
    const hours = pad(date.getHours());
    const minutes = pad(date.getMinutes());
    const seconds = pad(date.getSeconds());
    const millis = pad(date.getMilliseconds(), 3);

    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}.${millis}`;
}

let data = msg.payload;
if (typeof data === 'string') {
    try {
        data = JSON.parse(data);
    } catch (e) {
        node.error("Invalid JSON received from MQTT", e);
        return null; // Stops execution if JSON is broken
    }
}

const nowFormatted = formatForMySQLWithMillis(new Date());

msg.topic = "INSERT INTO iot.water_data (read_time, tds_ppm, depth_cm, tds_load, depth_load, write_time) VALUES (?, ?, ?, ?, ?, ?);";

msg.payload = [
    data.read_time ?? nowFormatted,
    data.tds_ppm ?? 0,      
    data.depth_cm ?? 0,      
    data.tds_load ?? 0,     
    data.depth_load ?? 0,   
    nowFormatted           
];

return msg;
