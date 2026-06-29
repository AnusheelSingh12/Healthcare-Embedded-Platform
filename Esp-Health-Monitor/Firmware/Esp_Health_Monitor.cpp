#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <OneWire.h>
#include <DallasTemperature.h>

#define HEART_PIN A0
#define ONE_WIRE_BUS 4    // D2 (GPIO4) for DS18B20 data
#define BPM_MIN 40
#define BPM_MAX 200
#define PULSE_THRESHOLD 550
#define BPM_JUMP_LIMIT 30
#define BPM_GRAPH 30

const char* ssid = "Health_Monitor";
const char* password = "patient123";

OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);
ESP8266WebServer server(80);

int bpmCurve[BPM_GRAPH] = {0}, bpmPos = 0;
int bpm = 0, avgBpm = 0, bpmSum = 0, bpmCnt = 0;
float temp = 0;
unsigned long lastBeat = 0;

void handleRoot() {
  String html = R"rawliteral(
  <!DOCTYPE html>
  <html>
  <head>
  <meta name="viewport" content="width=400">
  <title>Patient Monitor</title>
  <style>
    body{margin:0;padding:0;background:#181c20;color:#ededed;font-family:Arial,sans-serif;}
    .main{max-width:400px;margin:30px auto;background:#232328;border-radius:12px;box-shadow:0 6px 26px #0007;padding:28px 14px;}
    h1{color:#B3B8C3;font-size:2em;margin-bottom:13px;text-align:center;}
    .label{color:#bbb;font-size:1em;}
    .temp{font-size:1.5em;color:#ffe877;font-weight:500;}
    .hrbpm{font-size:2em;font-weight:700;color:#ff393c;}
    .hravg{color:#bbb;font-size:1em;}
    .footer{margin:18px 0 3px 0;color:#757780;font-size:.97em;text-align:center;}
    .chart{background:#181a1e;border-radius:8px;width:99%;margin:18px auto;}
    .charttitle{color:#c2c8d7;font-size:1em;margin-bottom:3px;text-align:center;}
  </style>
  </head>
  <body>
  <div class="main">
    <h1>Health Monitor</h1>
    <div class="label">Temperature (°C):<br>
      <span class="temp" id="temp">--</span>
    </div>
    <div class="label" style="margin-top:20px;">Heart Rate (BPM):</div>
    <div class="hravg">Avg (last 10): <b id="avgbpm">--</b></div>
    <div class="hrbpm" id="curbpm">--</div>
    <div class="charttitle">BPM Trends (last 30 beats)</div>
    <canvas id="bpmchart" width="340" height="80" class="chart"></canvas>
    <div class="footer">ESP8266 WiFi: <b>Health_Monitor</b></div>
  </div>
  <script>
    let ctx=document.getElementById("bpmchart").getContext("2d");
    function drawBpm(buf){
      ctx.clearRect(0,0,340,80);
      ctx.strokeStyle="#353535"; ctx.lineWidth=1;
      for(let y=0;y<=80;y+=20){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(340,y);ctx.stroke();}
      for(let x=0;x<=340;x+=34){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,80);ctx.stroke();}
      ctx.beginPath(); ctx.strokeStyle="#ff393c"; ctx.lineWidth=2.2;
      for(let i=0;i<buf.length;i++){
        let v=Math.max(40,Math.min(190,buf[i]));
        let y=80 - (v-40)/150*72;
        if(i===0)ctx.moveTo(i*11+6,y);
        else ctx.lineTo(i*11+6,y);
      }
      ctx.stroke();
    }
    function update(){
      fetch("/data").then(r=>r.json()).then(d=>{
        document.getElementById("temp").innerText=d.temp==null?'--':d.temp;
        document.getElementById("curbpm").innerText=d.bpm?d.bpm:"--";
        document.getElementById("avgbpm").innerText=d.avbpm?d.avbpm:"--";
        drawBpm(d.bpmarr);
      });
    }
    setInterval(update,1800); setTimeout(update,500);
  </script>
  </body></html>
  )rawliteral";
  server.send(200,"text/html",html);
}

void handleData() {
  String out = "{";
  out += "\"temp\":"; out += isnan(temp)? "null": String(temp,1);
  out += ",\"bpm\":"; out += bpm;
  out += ",\"avbpm\":"; out += avgBpm;
  out += ",\"bpmarr\":[";
  for(int i=0;i<BPM_GRAPH;i++) {
    out += String(bpmCurve[(bpmPos+i)%BPM_GRAPH]);
    if(i<BPM_GRAPH-1) out += ",";
  }
  out += "]}";
  server.send(200, "application/json", out);
}

void setup() {
  Serial.begin(115200);
  sensors.begin();
  WiFi.mode(WIFI_AP);
  WiFi.softAP(ssid, password);
  delay(400);
  server.on("/", handleRoot);
  server.on("/data", handleData);
  server.begin();
}

void loop() {
  static unsigned long t_hr = 0, t_temp = 0;
  static bool prevAbove = false;
  static int lastGoodBpm = 0;

  if(millis() - t_hr > 35) {
    t_hr = millis();
    int val = analogRead(HEART_PIN);
    bool nowAbove = (val > PULSE_THRESHOLD);

    if(nowAbove && !prevAbove) {
      unsigned long now = millis();
      if(lastGoodBpm > 0 && (now-lastGoodBpm)<300) ; // Ignore too-fast pulses
      else if(lastBeat > 0 && (now-lastBeat)>300) {
        int bpmNow = 60000/(now-lastBeat);
        int diff = (bpmNow > avgBpm) ? bpmNow-avgBpm : avgBpm-bpmNow;
        if(bpmNow>=BPM_MIN && bpmNow<=BPM_MAX && (avgBpm==0 || diff<BPM_JUMP_LIMIT)) {
          bpm = bpmNow;
          bpmCurve[bpmPos++] = bpm;
          if(bpmPos>=BPM_GRAPH) bpmPos=0;
          bpmSum += bpm; bpmCnt++;
          if(bpmCnt>10) { bpmSum -= bpmSum/bpmCnt; bpmCnt=10; }
          avgBpm = bpmSum/bpmCnt;
          lastGoodBpm=now;
        }
      }
      lastBeat = now;
    }
    prevAbove = nowAbove;
  }

  if(millis() - t_temp > 2000) {
    t_temp = millis();
    sensors.requestTemperatures();
    temp = sensors.getTempCByIndex(0);
  }
  server.handleClient();
}
