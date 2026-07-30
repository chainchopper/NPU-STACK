// NIRVANA FLEET AGENT — AMB82-Mini + Waveshare 2.4" ILI9341
#include "nirvana_config.h"
#include "nirvana_ili9341.h"
#include "nirvana_wifi.h"

unsigned long lastStatus=0,lastDisplay=0;
int page=0;

void setup(){
    Serial.begin(115200);delay(1000);
    Serial.println("\n=== NIRVANA FLEET — AMB82-Mini + ILI9341 ===");
    Serial.print("Version: ");Serial.println(NIRVANA_VERSION);

    // Ameba SPI: use transaction API (portable across all Arduino cores)
    SPI.begin();

    Serial.println("\n--- Display ---");
    if(nirvana_display_init())nirvana_center("BOOTING...",140,0x07E0,2);

    Serial.println("\n--- Network ---");
    if(nirvana_wifi_connect())nirvana_mqtt_connect();

    Serial.println("\n>>> AGENT READY <<<\n");
}

void loop(){
    nirvana_mqtt_loop();
    unsigned long now=millis();

    if(now-lastStatus>30000){lastStatus=now;nirvana_publish_status();}
    if(now-lastDisplay>5000){
        lastDisplay=now;page=(page+1)%3;
        char ip[20],ssid[40];
        snprintf(ip,sizeof(ip),"%d.%d.%d.%d",WiFi.localIP()[0],WiFi.localIP()[1],WiFi.localIP()[2],WiFi.localIP()[3]);
        strncpy(ssid,WiFi.SSID(),sizeof(ssid)-1);ssid[sizeof(ssid)-1]=0;
        if(page==0)     nirvana_page_status(ip,ssid,WiFi.RSSI(),mqttConnected);
        else if(page==1)nirvana_page_network(ip,ssid,WiFi.RSSI());
        else            nirvana_page_fleet(mqttConnected,now/1000);
    }
    delay(10);
}
