'use client';

import React, { useState, useEffect } from 'react';
import { User, Mail, Shield, Calendar, Save, Lock, Eye, EyeOff, Check, X } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { useAuth } from '@/lib/auth-context';
import { updateProfile, changePassword, uploadAvatar } from '@/lib/api';
import { formatDateTR } from '@/lib/utils';

const PRESET_AVATARS = [
  { name: 'Trader 1', url: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=120&h=120&q=80' },
  { name: 'Trader 2', url: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=120&h=120&q=80' },
  { name: 'Trader 3', url: 'https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?auto=format&fit=crop&w=120&h=120&q=80' },
  { name: 'Trader 4', url: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=120&h=120&q=80' },
  { name: 'AI Cat', url: 'https://robohash.org/trader1?set=set4' },
  { name: 'AI Dog', url: 'https://robohash.org/trader2?set=set4' },
  { name: 'AI Bear', url: 'https://robohash.org/trader3?set=set4' },
  { name: 'AI Owl', url: 'https://robohash.org/trader4?set=set4' },
];

export default function ProfilePage() {
  const { user, refresh } = useAuth();

  const [fullName, setFullName] = useState('');
  const [avatarUrl, setAvatarUrl] = useState('');
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileMsg, setProfileMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');

  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [changingPw, setChangingPw] = useState(false);
  const [pwMsg, setPwMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (user) {
      setFullName(user.full_name ?? '');
      setAvatarUrl(user.avatar_url ?? '');
    }
  }, [user]);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setUploadError('');
    try {
      const res = await uploadAvatar(file);
      setAvatarUrl(res.avatar_url);
    } catch (err: any) {
      setUploadError('Yükleme başarısız oldu: ' + (err?.message ?? 'hata'));
    } finally {
      setUploading(false);
    }
  };

  const saveProfile = async () => {
    setSavingProfile(true);
    setProfileMsg(null);
    try {
      await updateProfile({ full_name: fullName, avatar_url: avatarUrl });
      await refresh();
      setProfileMsg({ ok: true, text: 'Profil güncellendi.' });
    } catch (e: any) {
      setProfileMsg({ ok: false, text: 'Güncellenemedi: ' + (e?.message ?? 'hata') });
    } finally {
      setSavingProfile(false);
      setTimeout(() => setProfileMsg(null), 4000);
    }
  };

  const submitPasswordChange = async () => {
    setPwMsg(null);
    if (newPw.length < 8) {
      setPwMsg({ ok: false, text: 'Yeni şifre en az 8 karakter olmalı.' });
      return;
    }
    if (newPw !== confirmPw) {
      setPwMsg({ ok: false, text: 'Yeni şifreler eşleşmiyor.' });
      return;
    }
    setChangingPw(true);
    try {
      await changePassword(currentPw, newPw);
      setCurrentPw(''); setNewPw(''); setConfirmPw('');
      setPwMsg({ ok: true, text: 'Şifre güncellendi.' });
    } catch (e: any) {
      const msg = e?.message ?? '';
      if (msg.includes('401')) setPwMsg({ ok: false, text: 'Mevcut şifre hatalı.' });
      else if (msg.includes('400')) setPwMsg({ ok: false, text: 'Bu hesap OAuth ile giriş yapıyor; şifre yok.' });
      else setPwMsg({ ok: false, text: 'İşlem başarısız.' });
    } finally {
      setChangingPw(false);
      setTimeout(() => setPwMsg(null), 5000);
    }
  };

  if (!user) {
    return <div className="flex justify-center py-16"><div className="w-7 h-7 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" /></div>;
  }

  const initials = (user.full_name ?? user.email)[0]?.toUpperCase() ?? '?';
  const createdAt = (user as any).created_at;

  return (
    <div className="space-y-6 max-w-3xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-extrabold text-text-primary flex items-center gap-2">
          <User className="w-6 h-6 text-accent-primary" /> Profilim
        </h1>
        <p className="text-sm text-text-secondary mt-1">Hesap bilgilerini güncelle ve şifreni değiştir</p>
      </div>

      {/* Identity */}
      <GlassCard>
        <div className="flex items-center gap-4 mb-5">
          <div className="w-16 h-16 rounded-xl overflow-hidden bg-gradient-to-br from-amber to-accent-primary flex items-center justify-center text-2xl font-bold text-white flex-shrink-0">
            {user.avatar_url ? (
              <img src={user.avatar_url} alt="Avatar" className="w-full h-full object-cover" />
            ) : (
              initials
            )}
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-lg font-bold text-text-primary truncate">{user.full_name ?? user.email.split('@')[0]}</h2>
            <p className="text-sm text-text-muted truncate flex items-center gap-1.5">
              <Mail className="w-3.5 h-3.5" /> {user.email}
            </p>
          </div>
          {user.is_admin && (
            <span className="flex items-center gap-1 px-3 py-1 rounded-lg bg-amber/15 border border-amber/30 text-amber text-xs font-bold">
              <Shield className="w-3.5 h-3.5" /> ADMIN
            </span>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="bg-bg-secondary/50 rounded-xl p-3 border border-border-subtle">
            <p className="text-[10px] text-text-muted uppercase font-semibold">Giriş Yöntemi</p>
            <p className="text-sm font-semibold text-text-primary capitalize mt-0.5">{user.provider ?? 'email'}</p>
          </div>
          <div className="bg-bg-secondary/50 rounded-xl p-3 border border-border-subtle">
            <p className="text-[10px] text-text-muted uppercase font-semibold">Hesap Durumu</p>
            <p className={`text-sm font-semibold mt-0.5 ${user.is_active ? 'text-bullish' : 'text-bearish'}`}>
              {user.is_active ? 'Aktif' : 'Pasif'}
            </p>
          </div>
          {createdAt && (
            <div className="bg-bg-secondary/50 rounded-xl p-3 border border-border-subtle col-span-2">
              <p className="text-[10px] text-text-muted uppercase font-semibold flex items-center gap-1">
                <Calendar className="w-3 h-3" /> Üyelik Tarihi
              </p>
              <p className="text-sm font-semibold text-text-primary mt-0.5">
                {formatDateTR(createdAt)}
              </p>
            </div>
          )}
        </div>
      </GlassCard>

      {/* Update profile */}
      <GlassCard>
        <h3 className="text-sm font-bold text-text-primary mb-4">Profil Bilgileri</h3>
        <div className="space-y-3">
          <div>
            <label className="text-xs font-semibold text-text-muted uppercase">Ad Soyad</label>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full mt-1 px-3 py-2.5 text-sm bg-bg-secondary border border-border-subtle rounded-xl text-text-primary outline-none focus:border-accent-primary/40 transition-colors"
              placeholder="Adınız Soyadınız"
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-text-muted uppercase">Profil Fotoğrafı</label>
            
            {/* Presets Grid */}
            <div className="grid grid-cols-4 sm:grid-cols-8 gap-2 mt-2">
              {PRESET_AVATARS.map((preset, index) => (
                <button
                  key={index}
                  type="button"
                  onClick={() => setAvatarUrl(preset.url)}
                  className={`relative aspect-square rounded-xl overflow-hidden border-2 transition-all ${
                    avatarUrl === preset.url
                      ? 'border-accent-primary scale-95'
                      : 'border-border-subtle hover:border-border-medium'
                  }`}
                  title={preset.name}
                >
                  <img src={preset.url} alt={preset.name} className="w-full h-full object-cover" />
                  {avatarUrl === preset.url && (
                    <div className="absolute inset-0 bg-accent-primary/20 flex items-center justify-center">
                      <Check className="w-4 h-4 text-white bg-accent-primary rounded-full p-0.5" />
                    </div>
                  )}
                </button>
              ))}
            </div>

            {/* Custom URL Input */}
            <div className="mt-3">
              <label className="text-[11px] font-semibold text-text-muted uppercase">Veya Özel Fotoğraf URL'si</label>
              <input
                type="text"
                value={avatarUrl}
                onChange={(e) => setAvatarUrl(e.target.value)}
                className="w-full mt-1 px-3 py-2 text-xs bg-bg-secondary border border-border-subtle rounded-xl text-text-primary outline-none focus:border-accent-primary/40 transition-colors"
                placeholder="https://example.com/resim.png"
              />
            </div>

            {/* PC Upload */}
            <div className="mt-3 bg-bg-secondary/30 rounded-xl p-3 border border-border-subtle flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold text-text-primary">Bilgisayardan Fotoğraf Yükle</p>
                <p className="text-[10px] text-text-muted mt-0.5">PNG, JPG, WEBP veya GIF formatında dosya seçin.</p>
              </div>
              <div className="flex items-center gap-2">
                <label className="cursor-pointer px-3 py-1.5 rounded-lg bg-bg-tertiary border border-border-subtle hover:border-accent-primary/50 text-xs font-semibold text-text-primary transition-all flex items-center gap-1.5">
                  Dosya Seç
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handleFileChange}
                    className="hidden"
                  />
                </label>
                {uploading && (
                  <span className="text-[10px] text-text-muted animate-pulse">Yükleniyor...</span>
                )}
              </div>
            </div>
            {uploadError && (
              <p className="text-[10px] text-bearish mt-1">{uploadError}</p>
            )}
          </div>
          <div>
            <label className="text-xs font-semibold text-text-muted uppercase">E-posta</label>
            <input
              type="email"
              value={user.email}
              disabled
              className="w-full mt-1 px-3 py-2.5 text-sm bg-bg-tertiary/50 border border-border-subtle rounded-xl text-text-muted cursor-not-allowed"
            />
            <p className="text-[10px] text-text-muted mt-1">E-posta değiştirilemez (kimlik için sabit).</p>
          </div>
        </div>

        <div className="flex items-center gap-3 mt-5">
          <button
            onClick={saveProfile}
            disabled={savingProfile}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-accent-primary text-white text-sm font-semibold hover:bg-accent-hover transition-colors disabled:opacity-50"
          >
            <Save className="w-3.5 h-3.5" /> {savingProfile ? 'Kaydediliyor...' : 'Kaydet'}
          </button>
          {profileMsg && (
            <span className={`flex items-center gap-1.5 text-xs ${profileMsg.ok ? 'text-bullish' : 'text-bearish'}`}>
              {profileMsg.ok ? <Check className="w-3.5 h-3.5" /> : <X className="w-3.5 h-3.5" />}
              {profileMsg.text}
            </span>
          )}
        </div>
      </GlassCard>

      {/* Change password */}
      <GlassCard>
        <h3 className="text-sm font-bold text-text-primary mb-4 flex items-center gap-2">
          <Lock className="w-4 h-4 text-accent-primary" /> Şifre Değiştir
        </h3>
        <div className="space-y-3">
          <PasswordField
            label="Mevcut Şifre" value={currentPw} onChange={setCurrentPw}
            show={showCurrent} onToggle={() => setShowCurrent(!showCurrent)}
          />
          <PasswordField
            label="Yeni Şifre (min 8 karakter)" value={newPw} onChange={setNewPw}
            show={showNew} onToggle={() => setShowNew(!showNew)}
          />
          <PasswordField
            label="Yeni Şifre Tekrar" value={confirmPw} onChange={setConfirmPw}
            show={showNew} onToggle={() => setShowNew(!showNew)}
          />
        </div>
        <div className="flex items-center gap-3 mt-5">
          <button
            onClick={submitPasswordChange}
            disabled={changingPw || !currentPw || !newPw}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-accent-primary text-white text-sm font-semibold hover:bg-accent-hover transition-colors disabled:opacity-50"
          >
            <Lock className="w-3.5 h-3.5" /> {changingPw ? 'Güncelleniyor...' : 'Şifreyi Güncelle'}
          </button>
          {pwMsg && (
            <span className={`flex items-center gap-1.5 text-xs ${pwMsg.ok ? 'text-bullish' : 'text-bearish'}`}>
              {pwMsg.ok ? <Check className="w-3.5 h-3.5" /> : <X className="w-3.5 h-3.5" />}
              {pwMsg.text}
            </span>
          )}
        </div>
      </GlassCard>
    </div>
  );
}

function PasswordField({
  label, value, onChange, show, onToggle,
}: {
  label: string; value: string; onChange: (v: string) => void;
  show: boolean; onToggle: () => void;
}) {
  return (
    <div>
      <label className="text-xs font-semibold text-text-muted uppercase">{label}</label>
      <div className="relative mt-1">
        <input
          type={show ? 'text' : 'password'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full pl-3 pr-10 py-2.5 text-sm bg-bg-secondary border border-border-subtle rounded-xl text-text-primary outline-none focus:border-accent-primary/40 transition-colors font-mono"
          placeholder="••••••••"
        />
        <button
          type="button"
          onClick={onToggle}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
        >
          {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
        </button>
      </div>
    </div>
  );
}
