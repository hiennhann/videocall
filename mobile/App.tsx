import * as SecureStore from "expo-secure-store";
import {useCallback, useEffect, useMemo, useState} from "react";
import {
  ActivityIndicator, AppState, KeyboardAvoidingView, Platform, Pressable, ScrollView, StatusBar,
  StyleSheet, Text, TextInput, View, useColorScheme,
} from "react-native";
import {RTCView, type MediaStream} from "react-native-webrtc";
import {io, type Socket} from "socket.io-client";

import {accessToken, api, ApiError, clearSession, logout, origin, signIn, transfer} from "./src/api";
import type {Profile, PublicConfig} from "./src/api";
import {RoomCall, type RemoteVideo, type Room} from "./src/call";

type Theme = "light" | "dark";
type Styles = ReturnType<typeof makeStyles>;
type Selection = {room: Room; password: string};
const themeKey = "videocall.appearance";

function message(error: unknown) {
  return error instanceof Error ? error.message : "Đã xảy ra lỗi.";
}

function Action({title, onPress, styles, disabled = false}: {
  title: string; onPress: () => void; styles: Styles; disabled?: boolean;
}) {
  return <Pressable accessibilityRole="button" accessibilityState={{disabled}}
    onPress={onPress} disabled={disabled} style={[styles.button, disabled && styles.disabled]}>
    <Text style={styles.buttonLabel}>{title}</Text>
  </Pressable>;
}

function Field({label, value, onChange, styles, password = false, email = false}: {
  label: string; value: string; onChange: (value: string) => void; styles: Styles;
  password?: boolean; email?: boolean;
}) {
  return <View style={styles.field}>
    <Text style={styles.text}>{label}</Text>
    <TextInput accessibilityLabel={label} value={value} onChangeText={onChange}
      secureTextEntry={password} keyboardType={email ? "email-address" : "default"}
      autoCapitalize={email || password ? "none" : "sentences"}
      autoCorrect={!email && !password} style={styles.input}/>
  </View>;
}

function RoomPanel({selection, socket, styles, leave}: {
  selection: Selection; socket: Socket; styles: Styles; leave: (notice?: string) => void;
}) {
  const [status, setStatus] = useState("Đang chuẩn bị kết nối…");
  const [local, setLocal] = useState<MediaStream | null>(null);
  const [remotes, setRemotes] = useState<RemoteVideo[]>([]);
  const [call, setCall] = useState<RoomCall>();

  useEffect(() => {
    const controller = new RoomCall(socket, selection.room, selection.password, {
      local: setLocal, remotes: setRemotes, status: setStatus, closed: leave,
    });
    setCall(controller);
    let current = true;
    controller.start().catch(error => {
      controller.close();
      if (current) {
        setLocal(null);
        setStatus(message(error));
      }
    });
    return () => {
      current = false;
      controller.close();
    };
  }, [selection, socket, leave]);

  const meeting = selection.room.mode === "meeting";
  const mic = local?.getAudioTracks().some(track => track.enabled);
  const camera = local?.getVideoTracks().some(track => track.enabled);
  const [, redraw] = useState(0);
  const toggle = (kind: "audio" | "video", enabled: boolean) => {
    call?.toggle(kind, enabled);
    redraw(value => value + 1);
  };

  return <View style={styles.panel}>
    <Text style={styles.heading}>{selection.room.name || selection.room.code}</Text>
    <Text accessibilityLiveRegion="polite" style={styles.text}>{status}</Text>
    {remotes.map(({id, name, stream}) => <View key={id} style={styles.field}>
      <RTCView streamURL={stream.toURL()} style={styles.video} objectFit="contain"/>
      <Text style={styles.text}>{name}</Text>
    </View>)}
    {meeting && local && <>
      <RTCView streamURL={local.toURL()} mirror style={styles.localVideo} objectFit="cover"/>
      <View style={styles.actions}>
        <Action styles={styles} title={mic ? "Tắt mic" : "Bật mic"} onPress={() => toggle("audio", !mic)}/>
        <Action styles={styles} title={camera ? "Tắt camera" : "Bật camera"} onPress={() => toggle("video", !camera)}/>
      </View>
    </>}
    {!meeting && <Action styles={styles} title="Kết nối lại luồng xem" onPress={() => call?.retryViewing()}/>}
    <Action styles={styles} title="Rời phòng" onPress={() => leave()}/>
  </View>;
}

export default function App() {
  const systemTheme = useColorScheme();
  const [theme, setTheme] = useState<Theme>();
  const [config, setConfig] = useState<PublicConfig>();
  const [profile, setProfile] = useState<Profile>();
  const [socket, setSocket] = useState<Socket>();
  const [busy, setBusy] = useState(true);
  const [notice, setNotice] = useState("");
  const [registering, setRegistering] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [name, setName] = useState("");
  const [pending, setPending] = useState<string>();
  const [code, setCode] = useState("");
  const [summary, setSummary] = useState<Room>();
  const [roomPassword, setRoomPassword] = useState("");
  const [selection, setSelection] = useState<Selection>();
  const activeTheme = theme ?? (systemTheme === "dark" ? "dark" : "light");
  const styles = useMemo(() => makeStyles(activeTheme, config), [activeTheme, config]);

  const loadConfig = () => api<PublicConfig>("/config/public").then(setConfig);
  const loadProfile = () => api<Profile>("/me", {authenticated: true}).then(setProfile);
  const leave = useCallback((text = "") => {
    setSelection(undefined);
    setSummary(undefined);
    setRoomPassword("");
    setNotice(text);
  }, []);

  useEffect(() => {
    void SecureStore.getItemAsync(themeKey).then(value => {
      if (value === "light" || value === "dark") setTheme(value);
    }).catch(() => {});
    void loadConfig().catch(error => setNotice(message(error)));
    void loadProfile().catch(error => {
      if (!(error instanceof ApiError) || error.status !== 401) setNotice(message(error));
    }).finally(() => setBusy(false));
    const appState = AppState.addEventListener("change", state => {
      if (state === "active") void loadConfig().catch(() => {});
    });
    return () => appState.remove();
  }, []);

  useEffect(() => {
    if (!profile || profile.must_change_password) return;
    const connected = io(origin, {
      transports: ["websocket"],
      auth: done => accessToken().then(token => done({token}), () => done({})),
    });
    setSocket(connected);
    connected.on("force_disconnect", ({reason}) => {
      connected.disconnect();
      void clearSession().catch(() => {});
      setProfile(undefined);
      leave(reason === "DEVICE_SESSION_REPLACED"
        ? "Tài khoản đã được chuyển sang thiết bị khác."
        : "Phiên đã bị thu hồi. Vui lòng đăng nhập lại.");
    });
    connected.on("connect_error", error => {
      if (connected.active) return;
      if (["TOKEN_INVALID", "UNAUTHENTICATED", "ACCOUNT_DISABLED"].includes(error.data?.code)) {
        void clearSession().catch(() => {});
        setProfile(undefined);
        leave("Phiên đã hết hiệu lực. Vui lòng đăng nhập lại.");
      } else {
        setNotice(error.message);
      }
    });
    return () => {
      connected.disconnect();
      setSocket(current => current === connected ? undefined : current);
    };
  }, [profile, leave]);

  async function perform(work: () => Promise<void>) {
    setBusy(true);
    setNotice("");
    try {
      await work();
    } catch (error) {
      setNotice(message(error));
    } finally {
      setBusy(false);
    }
  }

  const submitAccount = () => perform(async () => {
    if (registering) {
      await api("/auth/register", {method: "POST", body: {email, password, display_name: name}});
      setRegistering(false);
      setPassword("");
      setNotice("Đã tạo tài khoản. Bạn có thể đăng nhập.");
      return;
    }
    try {
      await signIn(email, password);
      setPassword("");
      await loadProfile();
    } catch (error) {
      if (error instanceof ApiError && error.code === "DEVICE_TRANSFER_REQUIRED") {
        setPassword("");
        setPending(error.details.transfer_token);
        return;
      }
      throw error;
    }
  });

  const changeDevice = (action: "confirm" | "cancel") => perform(async () => {
    if (!pending) return;
    setPending(undefined);
    await transfer(pending, action);
    if (action === "confirm") await loadProfile();
  });

  const lookup = () => perform(async () => {
    const roomCode = code.trim().toLowerCase();
    if (!/^[a-z]{3}-[a-z]{4}-[a-z]{3}$/.test(roomCode)) throw new Error("Mã phòng không hợp lệ.");
    const room = await api<Room>("/rooms/" + roomCode, {authenticated: true});
    if (room.status === "closed") throw new Error("Phòng đã đóng.");
    setSummary(room);
    setRoomPassword("");
  });

  const saveTheme = () => {
    const next = activeTheme === "dark" ? "light" : "dark";
    setTheme(next);
    void SecureStore.setItemAsync(themeKey, next).catch(error => setNotice(message(error)));
  };

  const title = config?.project_name || "Videocall";
  return <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === "ios" ? "padding" : undefined}>
    <StatusBar barStyle={activeTheme === "dark" ? "light-content" : "dark-content"}/>
    <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.page}>
      <View style={styles.header}>
        <Text style={styles.title}>{title}</Text>
        <Action styles={styles} title={activeTheme === "dark" ? "Giao diện sáng" : "Giao diện tối"} onPress={saveTheme}/>
      </View>
      {busy && <ActivityIndicator accessibilityLabel="Đang xử lý"/>}
      {!!notice && <Text accessibilityLiveRegion="polite" style={styles.text}>{notice}</Text>}
      {config?.maintenance_mode && <Text style={styles.text}>{config.maintenance_message || "Hệ thống đang bảo trì."}</Text>}
      {!profile && (pending ? <View style={styles.panel}>
        <Text style={styles.heading}>Chuyển thiết bị</Text>
        <Text style={styles.text}>Tiếp tục sẽ đăng xuất thiết bị đang dùng tài khoản này và kết thúc cuộc gọi trên thiết bị đó.</Text>
        <Action styles={styles} title="Chuyển sang thiết bị này" disabled={busy} onPress={() => void changeDevice("confirm")}/>
        <Action styles={styles} title="Hủy" disabled={busy} onPress={() => void changeDevice("cancel")}/>
      </View> : <View style={styles.panel}>
        <Text style={styles.heading}>{registering ? "Tạo tài khoản" : "Đăng nhập"}</Text>
        {registering && <Field label="Tên hiển thị" value={name} onChange={setName} styles={styles}/>}
        <Field label="Email" value={email} onChange={setEmail} styles={styles} email/>
        <Field label="Mật khẩu" value={password} onChange={setPassword} styles={styles} password/>
        <Action styles={styles} title={registering ? "Đăng ký" : "Đăng nhập"}
          disabled={busy || !email.trim() || !password || (registering && !name.trim())}
          onPress={() => void submitAccount()}/>
        {(registering || config?.allow_registration !== false) &&
          <Action styles={styles} title={registering ? "Quay lại đăng nhập" : "Tạo tài khoản"}
            disabled={busy} onPress={() => setRegistering(value => !value)}/>}
      </View>)}
      {profile && (profile.must_change_password ? <View style={styles.panel}>
        <Text style={styles.heading}>Đổi mật khẩu</Text>
        <Field label="Mật khẩu hiện tại" value={password} onChange={setPassword} styles={styles} password/>
        <Field label="Mật khẩu mới" value={newPassword} onChange={setNewPassword} styles={styles} password/>
        <Action styles={styles} title="Lưu mật khẩu" disabled={busy || !password || !newPassword}
          onPress={() => void perform(async () => {
            await api("/me/password", {method: "POST", authenticated: true,
              body: {current_password: password, new_password: newPassword}});
            setPassword("");
            setNewPassword("");
            await loadProfile();
          })}/>
      </View> : selection && socket ? <RoomPanel selection={selection} socket={socket} styles={styles} leave={leave}/> :
        <View style={styles.panel}>
          <Text style={styles.heading}>Phòng gọi</Text>
          <Text style={styles.text}>{profile.display_name}</Text>
          {summary ? <>
            <Text style={styles.text}>{summary.name || summary.code}</Text>
            {summary.has_password && <Field label="Mật khẩu phòng" value={roomPassword} onChange={setRoomPassword}
              styles={styles} password/>}
            <Action styles={styles} title={summary.mode === "meeting" ? "Vào phòng và bật camera" : "Xem livestream"}
              disabled={!socket || (summary.has_password && !roomPassword)}
              onPress={() => setSelection({room: summary, password: roomPassword})}/>
            <Action styles={styles} title="Nhập mã khác" onPress={() => setSummary(undefined)}/>
          </> : <>
            <Field label="Mã phòng" value={code} onChange={setCode} styles={styles}/>
            <Action styles={styles} title="Tìm phòng" disabled={busy || !code.trim()} onPress={() => void lookup()}/>
          </>}
        </View>)}
      {profile && !selection && <Action styles={styles} title="Đăng xuất" disabled={busy} onPress={() => void perform(async () => {
        try { await logout(); }
        finally { setProfile(undefined); leave(); }
      })}/>}
    </ScrollView>
  </KeyboardAvoidingView>;
}

function makeStyles(theme: Theme, config?: PublicConfig) {
  const dark = theme === "dark";
  const base = dark ? "#121823" : "#f0f4f9";
  const surface = dark ? "#1a2535" : "#ffffff";
  const foreground = dark ? "#f2f6fc" : "#132237";
  const border = dark ? "#526279" : "#a3b1c2";
  const brand = config?.brand_color && /^#[a-f\d]{6}$/i.test(config.brand_color)
    ? config.brand_color : "#15768d";
  const fontFamily = config?.brand_font === "serif" ? Platform.select({ios: "Georgia", default: "serif"})
    : config?.brand_font === "monospace" ? Platform.select({ios: "Menlo", default: "monospace"}) : undefined;
  return StyleSheet.create({
    screen: {flex: 1, backgroundColor: base, paddingTop: Platform.OS === "android" ? StatusBar.currentHeight : 0},
    page: {padding: 20, paddingTop: Platform.OS === "ios" ? 56 : 20, gap: 16, width: "100%", maxWidth: 650, alignSelf: "center"},
    header: {gap: 10, paddingBottom: 14, borderBottomColor: brand, borderBottomWidth: 3},
    panel: {backgroundColor: surface, padding: 16, borderRadius: 16, gap: 14},
    heading: {color: foreground, fontFamily, fontSize: 22, fontWeight: "700"},
    title: {color: foreground, fontFamily, fontSize: 30, fontWeight: "800"},
    field: {gap: 6},
    text: {color: foreground, fontFamily, fontSize: 16, lineHeight: 23},
    input: {color: foreground, fontFamily, borderColor: border, borderWidth: 1, borderRadius: 10, padding: 12, fontSize: 16},
    actions: {flexDirection: "row", flexWrap: "wrap", gap: 8},
    button: {borderColor: brand, borderWidth: 1, borderRadius: 10, padding: 12, alignItems: "center"},
    buttonLabel: {color: foreground, fontFamily, fontWeight: "700", fontSize: 15},
    disabled: {opacity: 0.4},
    video: {width: "100%", aspectRatio: 16 / 9, backgroundColor: "#101010"},
    localVideo: {width: "52%", aspectRatio: 4 / 3, backgroundColor: "#101010"},
  });
}
