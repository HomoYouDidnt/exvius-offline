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
 * the game itself starts straight from the main icon. The same screen holds the game speed setting and
 * the summon rate multipliers (written to files/exvius/gacha_tweaks.json, read by server/gacha_tweaks.py).
 */
public final class SaveTransferActivity extends Activity {
    private static final int EXPORT = 1, IMPORT = 2;
    private static final long MAX_SAVE = 64L * 1024 * 1024;
    private static final int KEEP_AUTO_BACKUPS = 5;
    static final String[] SPEEDS = {"1", "1.5", "2", "3"};
    // Summon weight multipliers. RARE scales every 5, 6 and 7 (Neo Vision) star unit; FEATURED scales a
    // banner's rate-up units on top. Weights are normalised per draw, so 5x on a 1% tier is about 4.8%.
    static final String[] RARE = {"1", "2", "5", "10"};
    static final String[] FEATURED = {"1", "2", "4"};
    private static final String[] RARE_RARITIES = {"5", "6", "7"};
    private String rare = "1", featured = "1";
    private TextView status;

    static String speed(android.content.Context context) {
        String value = context.getSharedPreferences("exvius_settings", MODE_PRIVATE).getString("game_speed", "1");
        return Arrays.asList(SPEEDS).contains(value) ? value : "1";
    }

    static File tweaksFile(android.content.Context context) {
        return new File(context.getFilesDir(), "exvius/gacha_tweaks.json");
    }

    /** {rare, featured} when the file holds one of this screen's choices (no file = {"1","1"}), else null. */
    static String[] readTweaks(android.content.Context context) {
        File file = tweaksFile(context);
        if (!file.isFile()) return new String[]{"1", "1"};
        try {
            JSONObject root = new JSONObject(new String(readAll(new FileInputStream(file)), StandardCharsets.UTF_8));
            JSONObject rarity = root.optJSONObject("rarity_multiplier");
            String rareValue = "1";
            if (rarity != null && rarity.length() > 0) {
                if (rarity.length() != RARE_RARITIES.length) return null;
                rareValue = number(rarity.optDouble(RARE_RARITIES[0], -1));
                for (String key : RARE_RARITIES)
                    if (!number(rarity.optDouble(key, -1)).equals(rareValue)) return null;
            }
            String featuredValue = number(root.optDouble("featured_multiplier", 1));
            if (!Arrays.asList(RARE).contains(rareValue) || !Arrays.asList(FEATURED).contains(featuredValue)) return null;
            return new String[]{rareValue, featuredValue};
        } catch (Exception error) {
            return null;
        }
    }

    private static String number(double value) {
        return value == Math.rint(value) ? String.valueOf((long) value) : String.valueOf(value);
    }

    /** Writes the summon multipliers atomically; both at 1 removes the file (the banner's own rates). */
    static void writeTweaks(android.content.Context context, String rareValue, String featuredValue) throws Exception {
        File file = tweaksFile(context);
        if ("1".equals(rareValue) && "1".equals(featuredValue)) {
            if (file.isFile() && !file.delete()) throw new IOException("Could not reset the summon rates");
            return;
        }
        JSONObject rarity = new JSONObject();
        if (!"1".equals(rareValue))
            for (String key : RARE_RARITIES) rarity.put(key, Double.parseDouble(rareValue));
        JSONObject root = new JSONObject();
        root.put("rarity_multiplier", rarity);
        root.put("featured_multiplier", Double.parseDouble(featuredValue));
        File folder = file.getParentFile();
        if (folder != null && !folder.isDirectory() && !folder.mkdirs()) throw new IOException("Cannot create the data folder");
        File partial = new File(folder, "gacha_tweaks.json.tmp");
        try (FileOutputStream output = new FileOutputStream(partial)) {
            output.write(root.toString(2).getBytes(StandardCharsets.UTF_8));
            output.getFD().sync();
        }
        android.system.Os.rename(partial.getPath(), file.getPath());
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
        page.addView(label("Game speed (whole game, applies within a few seconds)", 0));
        page.addView(choices(SPEEDS, speed(this), 1000, value -> {
            getSharedPreferences("exvius_settings", MODE_PRIVATE).edit().putString("game_speed", value).apply();
            status.setText("Game speed set to " + value + "x.");
        }));
        String[] tweaks = readTweaks(this);
        boolean custom = tweaks == null;
        if (!custom) { rare = tweaks[0]; featured = tweaks[1]; }
        TextView rareLabel = label(custom ?
            "Summon rates: a custom gacha_tweaks.json is in use. Picking an option below replaces it.\n\n5\u2605 and Neo Vision chance" :
            "Summon rates (the Drop Rates screen shows the exact odds)\n\n5\u2605 and Neo Vision chance", padding);
        page.addView(rareLabel);
        page.addView(choices(RARE, custom ? "" : rare, 2000, value -> saveTweaks(value, featured)));
        page.addView(label("Rate-up units on top of that", 0));
        page.addView(choices(FEATURED, custom ? "" : featured, 3000, value -> saveTweaks(rare, value)));
        page.addView(label("Save backup", padding));
        Button export = new Button(this);
        export.setText("Export save to a file");
        export.setOnClickListener(view -> startExport());
        page.addView(export);
        Button restore = new Button(this);
        restore.setText("Import save from a file");
        restore.setOnClickListener(view -> startImport());
        page.addView(restore);
        android.widget.ScrollView scroll = new android.widget.ScrollView(this);
        scroll.setFillViewport(true);
        scroll.addView(page);
        setContentView(scroll);
        describe();
    }

    private interface Choice { void picked(String value); }

    private TextView label(String text, int top) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextSize(15);
        view.setGravity(Gravity.CENTER);
        view.setPadding(0, top, 0, 0);
        return view;
    }

    /** One row of radio buttons labelled "<value>x"; ids are base + index so each row stays distinct. */
    private RadioGroup choices(String[] values, String current, int base, Choice onPick) {
        RadioGroup group = new RadioGroup(this);
        group.setOrientation(RadioGroup.HORIZONTAL);
        group.setGravity(Gravity.CENTER);
        for (int i = 0; i < values.length; i++) {
            RadioButton option = new RadioButton(this);
            option.setId(base + i);
            option.setText(values[i] + "x");
            option.setChecked(values[i].equals(current));
            group.addView(option);
        }
        group.setOnCheckedChangeListener((view, id) -> {
            int index = id - base;
            if (index >= 0 && index < values.length) onPick.picked(values[index]);
        });
        return group;
    }

    private void saveTweaks(String rareValue, String featuredValue) {
        try {
            writeTweaks(this, rareValue, featuredValue);
            rare = rareValue;
            featured = featuredValue;
            status.setText("1".equals(rareValue) && "1".equals(featuredValue) ?
                "Summon rates are back to each banner's own rates." :
                "Summon rates: 5\u2605/NV x" + rareValue + ", rate-up units x" + featuredValue +
                ". Applies from your next summon.");
        } catch (Exception error) {
            android.util.Log.w("ExviusSave", "Summon rate setting failed", error);
            status.setText("Couldn't save the summon rates: " +
                (error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage()));
        }
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
