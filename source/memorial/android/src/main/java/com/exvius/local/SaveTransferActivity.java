package com.exvius.local;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.TextView;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Arrays;
import java.util.Date;
import java.util.Locale;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;
import org.json.JSONObject;

/**
 * Copies the campaign save to and from a file the player picks (Downloads, Drive, an SD card...).
 *
 * The save lives in the app's private storage, so uninstalling the app or clearing its storage erases it,
 * and a build signed with a different key can only be installed after uninstalling. This screen is the
 * way to carry a save across any of those. It has its own launcher icon ("Exvius Settings") because
 * the game itself starts straight from the main icon. The same screen holds the game speed setting.
 */
public final class SaveTransferActivity extends Activity {
    private static final int EXPORT = 1, IMPORT = 2;
    private static final long MAX_SAVE = 64L * 1024 * 1024;
    private static final int KEEP_AUTO_BACKUPS = 5;
    static final String[] SPEEDS = {"1", "1.5", "2", "3"};
    private TextView status;

    static String speed(android.content.Context context) {
        String value = context.getSharedPreferences("exvius_settings", MODE_PRIVATE).getString("game_speed", "1");
        return Arrays.asList(SPEEDS).contains(value) ? value : "1";
    }

    static File stateDir(android.content.Context context) {
        return new File(context.getFilesDir(), "exvius/state");
    }
    static File saveFile(android.content.Context context) {
        return new File(stateDir(context), "campaign.json");
    }

    /** Called before the game opens: keep the last few launches' saves in case one gets damaged. */
    static void autoBackup(android.content.Context context) {
        try {
            File save = saveFile(context);
            if (!save.isFile() || save.length() == 0) return;
            File folder = new File(stateDir(context), "backups");
            if (!folder.isDirectory() && !folder.mkdirs()) return;
            String stamp = new SimpleDateFormat("yyyyMMdd-HHmmss", Locale.ROOT).format(new Date());
            copy(save, new File(folder, "auto-" + stamp + ".json"));
            File[] autos = folder.listFiles((dir, name) -> name.startsWith("auto-") && name.endsWith(".json"));
            if (autos != null && autos.length > KEEP_AUTO_BACKUPS) {
                Arrays.sort(autos, (a, b) -> a.getName().compareTo(b.getName()));
                for (int i = 0; i < autos.length - KEEP_AUTO_BACKUPS; i++) autos[i].delete();
            }
        } catch (Exception error) {
            android.util.Log.w("ExviusSave", "Automatic save backup skipped", error);
        }
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setGravity(Gravity.CENTER);
        int padding = (int) (24 * getResources().getDisplayMetrics().density);
        page.setPadding(padding, padding, padding, padding);
        TextView title = new TextView(this);
        title.setText("Exvius Settings");
        title.setTextSize(28);
        title.setGravity(Gravity.CENTER);
        page.addView(title);
        status = new TextView(this);
        status.setTextSize(17);
        status.setGravity(Gravity.CENTER);
        status.setPadding(0, padding, 0, padding);
        page.addView(status);
        TextView speedLabel = new TextView(this);
        speedLabel.setText("Game speed (whole game, applies within a few seconds)");
        speedLabel.setTextSize(15);
        speedLabel.setGravity(Gravity.CENTER);
        page.addView(speedLabel);
        RadioGroup speeds = new RadioGroup(this);
        speeds.setOrientation(RadioGroup.HORIZONTAL);
        speeds.setGravity(Gravity.CENTER);
        String current = speed(this);
        for (int i = 0; i < SPEEDS.length; i++) {
            RadioButton option = new RadioButton(this);
            option.setId(1000 + i);
            option.setText(SPEEDS[i] + "x");
            option.setChecked(SPEEDS[i].equals(current));
            speeds.addView(option);
        }
        speeds.setOnCheckedChangeListener((group, id) -> {
            int index = id - 1000;
            if (index < 0 || index >= SPEEDS.length) return;
            getSharedPreferences("exvius_settings", MODE_PRIVATE).edit()
                .putString("game_speed", SPEEDS[index]).apply();
            status.setText("Game speed set to " + SPEEDS[index] + "x.");
        });
        page.addView(speeds);
        TextView saveLabel = new TextView(this);
        saveLabel.setText("Save backup");
        saveLabel.setTextSize(15);
        saveLabel.setGravity(Gravity.CENTER);
        saveLabel.setPadding(0, padding, 0, 0);
        page.addView(saveLabel);
        Button export = new Button(this);
        export.setText("Export save to a file");
        export.setOnClickListener(view -> startExport());
        page.addView(export);
        Button restore = new Button(this);
        restore.setText("Import save from a file");
        restore.setOnClickListener(view -> startImport());
        page.addView(restore);
        setContentView(page);
        describe();
    }

    private void describe() {
        File save = saveFile(this);
        status.setText(save.isFile() ?
            "Your save was last written " + new SimpleDateFormat("MMM d, h:mm a", Locale.getDefault())
                .format(new Date(save.lastModified())) + ".\n\nExport a copy before uninstalling, clearing storage " +
                "or installing a build from a different source." :
            "No save yet. Start the game once, or import a save you exported earlier.");
    }

    private void startExport() {
        if (!saveFile(this).isFile()) { status.setText("There is no save to export yet."); return; }
        String stamp = new SimpleDateFormat("yyyy-MM-dd-HHmm", Locale.ROOT).format(new Date());
        startActivityForResult(new Intent(Intent.ACTION_CREATE_DOCUMENT)
            .addCategory(Intent.CATEGORY_OPENABLE).setType("application/zip")
            .putExtra(Intent.EXTRA_TITLE, "exvius-save-" + stamp + ".zip"), EXPORT);
    }

    private void startImport() {
        if (DataUpdates.gameOpened() || LocalGameBridge.started()) {
            // The running game keeps the save in memory and would write over an imported file.
            status.setText("Exvius is still running. Swipe it away from your recent apps, then open " +
                "Exvius Settings again to import.");
            return;
        }
        startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT)
            .addCategory(Intent.CATEGORY_OPENABLE).setType("*/*")
            .putExtra(Intent.EXTRA_MIME_TYPES, new String[]{"application/zip", "application/json",
                "application/octet-stream"}), IMPORT);
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (result != RESULT_OK || data == null || data.getData() == null) return;
        Uri uri = data.getData();
        try {
            if (request == EXPORT) {
                exportTo(uri);
                status.setText("Save exported. Keep that file somewhere outside the app, like Drive or your PC.");
            } else if (request == IMPORT) {
                String name = importFrom(uri);
                status.setText("Imported the save for " + name + ". Your previous save was kept in the app's " +
                    "backups folder. Open Exvius to continue.");
            }
        } catch (Exception error) {
            android.util.Log.w("ExviusSave", "Save transfer failed", error);
            status.setText((request == EXPORT ? "Export failed: " : "Import failed, your current save is unchanged: ") +
                (error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage()));
        }
    }

    private void exportTo(Uri uri) throws IOException {
        byte[] save = readAll(new FileInputStream(saveFile(this)));
        try (OutputStream raw = getContentResolver().openOutputStream(uri, "w")) {
            if (raw == null) throw new IOException("Could not open the chosen file");
            try (ZipOutputStream zip = new ZipOutputStream(raw)) {
                zip.putNextEntry(new ZipEntry("campaign.json"));
                zip.write(save);
                zip.closeEntry();
                zip.putNextEntry(new ZipEntry("README.txt"));
                zip.write(("Exvius Offline save. Import it with the Exvius Settings icon.\n").getBytes(StandardCharsets.UTF_8));
                zip.closeEntry();
            }
        }
    }

    private String importFrom(Uri uri) throws Exception {
        byte[] candidate = null;
        try (InputStream raw = getContentResolver().openInputStream(uri)) {
            if (raw == null) throw new IOException("Could not open the chosen file");
            byte[] bytes = readAll(raw);
            if (bytes.length > 1 && bytes[0] == 'P' && bytes[1] == 'K') {
                try (ZipInputStream zip = new ZipInputStream(new java.io.ByteArrayInputStream(bytes))) {
                    for (ZipEntry entry; (entry = zip.getNextEntry()) != null; ) {
                        String name = entry.getName();
                        if (!entry.isDirectory() && (name.equals("campaign.json") || name.endsWith("/campaign.json"))) {
                            candidate = readAll(zip);
                            break;
                        }
                    }
                }
                if (candidate == null) throw new IOException("That ZIP has no campaign.json in it");
            } else {
                candidate = bytes;
            }
        }
        JSONObject parsed = new JSONObject(new String(candidate, StandardCharsets.UTF_8));
        if (!parsed.has("identity") || !parsed.has("roster"))
            throw new IOException("That file isn't an Exvius Offline save");
        String player = parsed.getJSONObject("identity").optString("handle_name", "your player");
        File folder = stateDir(this);
        if (!folder.isDirectory() && !folder.mkdirs()) throw new IOException("Cannot create the save folder");
        File save = saveFile(this);
        if (save.isFile()) {
            File backups = new File(folder, "backups");
            if (!backups.isDirectory() && !backups.mkdirs()) throw new IOException("Cannot back up the current save");
            copy(save, new File(backups, "before-import-" + System.currentTimeMillis() + ".json"));
        }
        File partial = new File(folder, "campaign.json.import");
        try (FileOutputStream output = new FileOutputStream(partial)) {
            output.write(candidate);
            output.getFD().sync();
        }
        android.system.Os.rename(partial.getPath(), save.getPath());
        return player;
    }

    private static byte[] readAll(InputStream input) throws IOException {
        try (InputStream in = input; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[65536];
            for (int count; (count = in.read(buffer)) != -1; ) {
                if (out.size() + count > MAX_SAVE) throw new IOException("That file is too large to be a save");
                out.write(buffer, 0, count);
            }
            return out.toByteArray();
        }
    }

    private static void copy(File from, File to) throws IOException {
        try (FileInputStream in = new FileInputStream(from); FileOutputStream out = new FileOutputStream(to)) {
            byte[] buffer = new byte[65536];
            for (int count; (count = in.read(buffer)) != -1; ) out.write(buffer, 0, count);
            out.getFD().sync();
        }
    }
}
