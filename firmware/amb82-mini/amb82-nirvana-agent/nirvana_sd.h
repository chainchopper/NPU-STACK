// NIRVANA SD CARD — FatFs file system for AMB82-Mini
// Reads/writes to microSD slot via built-in SD Host controller
#ifndef NIRVANA_SD_H
#define NIRVANA_SD_H

#include "ff.h"       // FatFs — bundled in Ameba SDK
#include "nirvana_config.h"

FATFS sdFs;
bool sdReady = false;

// ── Initialize SD card ──
bool nirvana_sd_init() {
    Serial.println("[SD] Mounting...");
    FRESULT res = f_mount(&sdFs, "", 1);  // 1 = mount now
    if (res == FR_OK) {
        sdReady = true;
        Serial.println("[SD] Mounted OK");
        return true;
    }
    Serial.print("[SD] Mount failed: "); Serial.println(res);
    return false;
}

// ── List files in root directory ──
// Fills the provided array with filenames. Returns count found (max 'maxFiles').
int nirvana_sd_list(char names[][32], int maxFiles) {
    if (!sdReady) return 0;
    DIR dir;
    FILINFO fno;
    int count = 0;

    FRESULT res = f_opendir(&dir, "/");
    if (res != FR_OK) return 0;

    while (count < maxFiles) {
        res = f_readdir(&dir, &fno);
        if (res != FR_OK || fno.fname[0] == 0) break;

        // Skip system dirs
        if (fno.fname[0] == '.') continue;

        snprintf(names[count], 32, "%s%s",
                 (fno.fattrib & AM_DIR) ? "[D] " : "",
                 fno.fname);
        count++;
    }
    f_closedir(&dir);
    return count;
}

// ── Read a file from SD into buffer ──
// Returns bytes read, 0 on failure
size_t nirvana_sd_read(const char* path, uint8_t* buf, size_t maxLen) {
    if (!sdReady) return 0;
    FIL fp;
    FRESULT res = f_open(&fp, path, FA_READ);
    if (res != FR_OK) { Serial.println("[SD] Open failed"); return 0; }

    UINT br;
    res = f_read(&fp, buf, maxLen, &br);
    f_close(&fp);

    if (res != FR_OK) return 0;
    return br;
}

// ── Free/total space in MB ──
void nirvana_sd_space(uint32_t* totalMB, uint32_t* freeMB) {
    if (!sdReady) { *totalMB = 0; *freeMB = 0; return; }
    FATFS* fs;
    DWORD fre_clust;
    FRESULT res = f_getfree("", &fre_clust, &fs);
    if (res == FR_OK) {
        *totalMB = (fs->n_fatent - 2) * fs->csize / 2048;  // 512-byte sectors → MB
        *freeMB  = fre_clust * fs->csize / 2048;
    }
}

#endif
