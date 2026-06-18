// ============================================
// TradeMinds AI - Internationalization System
// ============================================

import { Language } from '@/types';

export type TranslationKey = keyof typeof translations.tr;

const translations = {
  tr: {
    // ---- Navigation ----
    'nav.dashboard': 'Gösterge Paneli',
    'nav.signals': 'Sinyal Merkezi',
    'nav.markets': 'Piyasalar',
    'nav.watchlist': 'İzleme Listesi',
    'nav.portfolio': 'Portföy',
    'nav.alerts': 'Alarmlar',
    'nav.performance': 'Performans',
    'nav.settings': 'Ayarlar',
    'nav.analytics': 'Analitik',
    'nav.news': 'Haberler',

    // ---- Brand ----
    'brand.name': 'TradeMinds AI',
    'brand.tagline': 'Yapay Zeka Destekli Trading İstihbaratı',

    // ---- Signal Types ----
    'signal.strong_buy': 'Güçlü Al',
    'signal.buy': 'Al',
    'signal.hold': 'Tut',
    'signal.sell': 'Sat',
    'signal.strong_sell': 'Güçlü Sat',

    // ---- Signal Labels ----
    'signal.confidence': 'Güven Skoru',
    'signal.probability': 'Olasılık',
    'signal.risk': 'Risk',
    'signal.risk_level': 'Risk Seviyesi',
    'signal.entry_zone': 'Giriş Bölgesi',
    'signal.stop_loss': 'Zarar Durdur',
    'signal.take_profit': 'Kar Al',
    'signal.tp1': 'TP1',
    'signal.tp2': 'TP2',
    'signal.tp3': 'TP3',
    'signal.timeframe': 'Zaman Dilimi',
    'signal.direction': 'Yön',
    'signal.active': 'Aktif',
    'signal.expired': 'Süresi Dolmuş',
    'signal.generated_at': 'Oluşturulma',
    'signal.invalidation': 'Geçersizlik Koşulları',
    'signal.explanation': 'Açıklama',
    'signal.new_signal': 'Yeni Sinyal',
    'signal.all_signals': 'Tüm Sinyaller',
    'signal.active_signals': 'Aktif Sinyaller',
    'signal.latest_signals': 'Son Sinyaller',

    // ---- Direction ----
    'direction.bullish': 'Yükseliş',
    'direction.bearish': 'Düşüş',
    'direction.neutral': 'Nötr',

    // ---- Risk Levels ----
    'risk.low': 'Düşük',
    'risk.medium': 'Orta',
    'risk.high': 'Yüksek',
    'risk.very_high': 'Çok Yüksek',

    // ---- Engine Names ----
    'engine.technical': 'Teknik Analiz',
    'engine.fundamental': 'Temel Analiz',
    'engine.sentiment': 'Duygu Analizi',
    'engine.onchain': 'On-Chain Analiz',
    'engine.macro': 'Makro Analiz',
    'engine.findings': 'Önemli Bulgular',
    'engine.warnings': 'Uyarılar',

    // ---- Dashboard ----
    'dashboard.title': 'Gösterge Paneli',
    'dashboard.welcome': 'Hoş Geldiniz',
    'dashboard.overview': 'Piyasa Özeti',
    'dashboard.total_signals': 'Toplam Sinyal',
    'dashboard.win_rate': 'Kazanma Oranı',
    'dashboard.avg_return': 'Ort. Getiri',
    'dashboard.active_signals': 'Aktif Sinyaller',
    'dashboard.tracked_assets': 'İzlenen Varlıklar',
    'dashboard.market_mood': 'Piyasa Havası',
    'dashboard.fear_greed': 'Korku & Açgözlülük',
    'dashboard.trending': 'Trendler',
    'dashboard.top_performers': 'En İyi Performans',
    'dashboard.worst_performers': 'En Kötü Performans',
    'dashboard.recent_signals': 'Son Sinyaller',

    // ---- Markets ----
    'markets.title': 'Piyasalar',
    'markets.crypto': 'Kripto',
    'markets.stocks': 'Hisse Senetleri',
    'markets.forex': 'Forex',
    'markets.futures': 'Vadeli İşlemler',
    'markets.all': 'Tümü',
    'markets.price': 'Fiyat',
    'markets.change_24h': '24s Değişim',
    'markets.volume': 'Hacim',
    'markets.market_cap': 'Piyasa Değeri',
    'markets.dominance': 'Dominans',
    'markets.circulating_supply': 'Dolaşımdaki Arz',
    'markets.search_placeholder': 'Piyasa ara...',

    // ---- Watchlist ----
    'watchlist.title': 'İzleme Listesi',
    'watchlist.add': 'Varlık Ekle',
    'watchlist.remove': 'Kaldır',
    'watchlist.create': 'Liste Oluştur',
    'watchlist.empty': 'İzleme listeniz boş',
    'watchlist.empty_desc': 'Piyasaları takip etmek için varlık ekleyin',

    // ---- Portfolio ----
    'portfolio.title': 'Portföy',
    'portfolio.total_value': 'Toplam Değer',
    'portfolio.total_pnl': 'Toplam K/Z',
    'portfolio.allocation': 'Dağılım',
    'portfolio.quantity': 'Miktar',
    'portfolio.avg_entry': 'Ort. Giriş',
    'portfolio.current_value': 'Güncel Değer',
    'portfolio.pnl': 'K/Z',

    // ---- Alerts ----
    'alerts.title': 'Alarmlar',
    'alerts.create': 'Alarm Oluştur',
    'alerts.price_alert': 'Fiyat Alarmı',
    'alerts.signal_alert': 'Sinyal Alarmı',
    'alerts.custom_alert': 'Özel Alarm',
    'alerts.active': 'Aktif',
    'alerts.triggered': 'Tetiklendi',
    'alerts.none': 'Alarm yok',
    'alerts.none_desc': 'Fiyat değişimlerinden haberdar olmak için alarm ekleyin',

    // ---- Performance ----
    'performance.title': 'Performans',
    'performance.win': 'Kazanç',
    'performance.loss': 'Kayıp',
    'performance.breakeven': 'Başabaş',
    'performance.total_trades': 'Toplam İşlem',
    'performance.avg_return': 'Ort. Getiri',
    'performance.best_trade': 'En İyi İşlem',
    'performance.worst_trade': 'En Kötü İşlem',
    'performance.drawdown': 'Maksimum Düşüş',
    'performance.sharpe': 'Sharpe Oranı',
    'performance.history': 'İşlem Geçmişi',

    // ---- Settings ----
    'settings.title': 'Ayarlar',
    'settings.profile': 'Profil',
    'settings.notifications': 'Bildirimler',
    'settings.language': 'Dil',
    'settings.theme': 'Tema',
    'settings.api_keys': 'API Anahtarları',
    'settings.security': 'Güvenlik',
    'settings.preferences': 'Tercihler',
    'settings.save': 'Kaydet',
    'settings.cancel': 'İptal',

    // ---- Common Actions ----
    'common.search': 'Ara',
    'common.search_placeholder': 'Varlık, sinyal veya komut ara...',
    'common.filter': 'Filtrele',
    'common.sort': 'Sırala',
    'common.refresh': 'Yenile',
    'common.export': 'Dışa Aktar',
    'common.import': 'İçe Aktar',
    'common.delete': 'Sil',
    'common.edit': 'Düzenle',
    'common.save': 'Kaydet',
    'common.cancel': 'İptal',
    'common.confirm': 'Onayla',
    'common.close': 'Kapat',
    'common.back': 'Geri',
    'common.next': 'İleri',
    'common.loading': 'Yükleniyor...',
    'common.no_data': 'Veri bulunamadı',
    'common.error': 'Hata oluştu',
    'common.retry': 'Tekrar Dene',
    'common.view_all': 'Tümünü Gör',
    'common.view_details': 'Detayları Gör',
    'common.more': 'Daha Fazla',
    'common.less': 'Daha Az',
    'common.copy': 'Kopyala',
    'common.copied': 'Kopyalandı',
    'common.share': 'Paylaş',
    'common.download': 'İndir',

    // ---- Time ----
    'time.now': 'Şimdi',
    'time.minutes_ago': 'dakika önce',
    'time.hours_ago': 'saat önce',
    'time.days_ago': 'gün önce',
    'time.just_now': 'Az önce',

    // ---- Notifications ----
    'notifications.title': 'Bildirimler',
    'notifications.mark_all_read': 'Tümünü Okundu İşaretle',
    'notifications.empty': 'Bildirim yok',
    'notifications.new_signal': 'Yeni sinyal oluşturuldu',
    'notifications.alert_triggered': 'Alarm tetiklendi',

    // ---- Auth ----
    'auth.login': 'Giriş Yap',
    'auth.logout': 'Çıkış Yap',
    'auth.register': 'Kayıt Ol',
    'auth.profile': 'Profilim',
    'auth.account': 'Hesap',

    // ---- Tooltips ----
    'tooltip.collapse_sidebar': 'Kenar çubuğunu daralt',
    'tooltip.expand_sidebar': 'Kenar çubuğunu genişlet',
    'tooltip.toggle_language': 'Dili değiştir',
    'tooltip.notifications': 'Bildirimler',
    'tooltip.user_menu': 'Kullanıcı menüsü',

    // ---- Timeframes ----
    'timeframe.1m': '1 Dakika',
    'timeframe.5m': '5 Dakika',
    'timeframe.15m': '15 Dakika',
    'timeframe.1h': '1 Saat',
    'timeframe.4h': '4 Saat',
    'timeframe.1d': '1 Gün',
    'timeframe.1w': '1 Hafta',

    // ---- Empty States ----
    'empty.signals': 'Henüz sinyal yok',
    'empty.signals_desc': 'Yeni sinyaller oluşturulduğunda burada görünecek',
    'empty.watchlist': 'İzleme listesi boş',
    'empty.watchlist_desc': 'Takip etmek istediğiniz varlıkları ekleyin',
    'empty.alerts': 'Alarm ayarlanmamış',
    'empty.alerts_desc': 'Fiyat hareketlerinden haberdar olmak için alarm oluşturun',
    'empty.portfolio': 'Portföy boş',
    'empty.portfolio_desc': 'Portföyünüzü oluşturmak için varlık ekleyin',
  },

  en: {
    // ---- Navigation ----
    'nav.dashboard': 'Dashboard',
    'nav.signals': 'Signal Center',
    'nav.markets': 'Markets',
    'nav.watchlist': 'Watchlist',
    'nav.portfolio': 'Portfolio',
    'nav.alerts': 'Alerts',
    'nav.performance': 'Performance',
    'nav.settings': 'Settings',
    'nav.analytics': 'Analytics',
    'nav.news': 'News',

    // ---- Brand ----
    'brand.name': 'TradeMinds AI',
    'brand.tagline': 'AI-Powered Trading Intelligence',

    // ---- Signal Types ----
    'signal.strong_buy': 'Strong Buy',
    'signal.buy': 'Buy',
    'signal.hold': 'Hold',
    'signal.sell': 'Sell',
    'signal.strong_sell': 'Strong Sell',

    // ---- Signal Labels ----
    'signal.confidence': 'Confidence Score',
    'signal.probability': 'Probability',
    'signal.risk': 'Risk',
    'signal.risk_level': 'Risk Level',
    'signal.entry_zone': 'Entry Zone',
    'signal.stop_loss': 'Stop Loss',
    'signal.take_profit': 'Take Profit',
    'signal.tp1': 'TP1',
    'signal.tp2': 'TP2',
    'signal.tp3': 'TP3',
    'signal.timeframe': 'Timeframe',
    'signal.direction': 'Direction',
    'signal.active': 'Active',
    'signal.expired': 'Expired',
    'signal.generated_at': 'Generated At',
    'signal.invalidation': 'Invalidation Conditions',
    'signal.explanation': 'Explanation',
    'signal.new_signal': 'New Signal',
    'signal.all_signals': 'All Signals',
    'signal.active_signals': 'Active Signals',
    'signal.latest_signals': 'Latest Signals',

    // ---- Direction ----
    'direction.bullish': 'Bullish',
    'direction.bearish': 'Bearish',
    'direction.neutral': 'Neutral',

    // ---- Risk Levels ----
    'risk.low': 'Low',
    'risk.medium': 'Medium',
    'risk.high': 'High',
    'risk.very_high': 'Very High',

    // ---- Engine Names ----
    'engine.technical': 'Technical Analysis',
    'engine.fundamental': 'Fundamental Analysis',
    'engine.sentiment': 'Sentiment Analysis',
    'engine.onchain': 'On-Chain Analysis',
    'engine.macro': 'Macro Analysis',
    'engine.findings': 'Key Findings',
    'engine.warnings': 'Warnings',

    // ---- Dashboard ----
    'dashboard.title': 'Dashboard',
    'dashboard.welcome': 'Welcome',
    'dashboard.overview': 'Market Overview',
    'dashboard.total_signals': 'Total Signals',
    'dashboard.win_rate': 'Win Rate',
    'dashboard.avg_return': 'Avg. Return',
    'dashboard.active_signals': 'Active Signals',
    'dashboard.tracked_assets': 'Tracked Assets',
    'dashboard.market_mood': 'Market Mood',
    'dashboard.fear_greed': 'Fear & Greed',
    'dashboard.trending': 'Trending',
    'dashboard.top_performers': 'Top Performers',
    'dashboard.worst_performers': 'Worst Performers',
    'dashboard.recent_signals': 'Recent Signals',

    // ---- Markets ----
    'markets.title': 'Markets',
    'markets.crypto': 'Crypto',
    'markets.stocks': 'Stocks',
    'markets.forex': 'Forex',
    'markets.futures': 'Futures',
    'markets.all': 'All',
    'markets.price': 'Price',
    'markets.change_24h': '24h Change',
    'markets.volume': 'Volume',
    'markets.market_cap': 'Market Cap',
    'markets.dominance': 'Dominance',
    'markets.circulating_supply': 'Circulating Supply',
    'markets.search_placeholder': 'Search markets...',

    // ---- Watchlist ----
    'watchlist.title': 'Watchlist',
    'watchlist.add': 'Add Asset',
    'watchlist.remove': 'Remove',
    'watchlist.create': 'Create List',
    'watchlist.empty': 'Your watchlist is empty',
    'watchlist.empty_desc': 'Add assets to track the markets',

    // ---- Portfolio ----
    'portfolio.title': 'Portfolio',
    'portfolio.total_value': 'Total Value',
    'portfolio.total_pnl': 'Total P&L',
    'portfolio.allocation': 'Allocation',
    'portfolio.quantity': 'Quantity',
    'portfolio.avg_entry': 'Avg. Entry',
    'portfolio.current_value': 'Current Value',
    'portfolio.pnl': 'P&L',

    // ---- Alerts ----
    'alerts.title': 'Alerts',
    'alerts.create': 'Create Alert',
    'alerts.price_alert': 'Price Alert',
    'alerts.signal_alert': 'Signal Alert',
    'alerts.custom_alert': 'Custom Alert',
    'alerts.active': 'Active',
    'alerts.triggered': 'Triggered',
    'alerts.none': 'No alerts',
    'alerts.none_desc': 'Add alerts to stay informed about price changes',

    // ---- Performance ----
    'performance.title': 'Performance',
    'performance.win': 'Win',
    'performance.loss': 'Loss',
    'performance.breakeven': 'Breakeven',
    'performance.total_trades': 'Total Trades',
    'performance.avg_return': 'Avg. Return',
    'performance.best_trade': 'Best Trade',
    'performance.worst_trade': 'Worst Trade',
    'performance.drawdown': 'Max Drawdown',
    'performance.sharpe': 'Sharpe Ratio',
    'performance.history': 'Trade History',

    // ---- Settings ----
    'settings.title': 'Settings',
    'settings.profile': 'Profile',
    'settings.notifications': 'Notifications',
    'settings.language': 'Language',
    'settings.theme': 'Theme',
    'settings.api_keys': 'API Keys',
    'settings.security': 'Security',
    'settings.preferences': 'Preferences',
    'settings.save': 'Save',
    'settings.cancel': 'Cancel',

    // ---- Common Actions ----
    'common.search': 'Search',
    'common.search_placeholder': 'Search assets, signals or commands...',
    'common.filter': 'Filter',
    'common.sort': 'Sort',
    'common.refresh': 'Refresh',
    'common.export': 'Export',
    'common.import': 'Import',
    'common.delete': 'Delete',
    'common.edit': 'Edit',
    'common.save': 'Save',
    'common.cancel': 'Cancel',
    'common.confirm': 'Confirm',
    'common.close': 'Close',
    'common.back': 'Back',
    'common.next': 'Next',
    'common.loading': 'Loading...',
    'common.no_data': 'No data found',
    'common.error': 'An error occurred',
    'common.retry': 'Retry',
    'common.view_all': 'View All',
    'common.view_details': 'View Details',
    'common.more': 'More',
    'common.less': 'Less',
    'common.copy': 'Copy',
    'common.copied': 'Copied',
    'common.share': 'Share',
    'common.download': 'Download',

    // ---- Time ----
    'time.now': 'Now',
    'time.minutes_ago': 'minutes ago',
    'time.hours_ago': 'hours ago',
    'time.days_ago': 'days ago',
    'time.just_now': 'Just now',

    // ---- Notifications ----
    'notifications.title': 'Notifications',
    'notifications.mark_all_read': 'Mark All as Read',
    'notifications.empty': 'No notifications',
    'notifications.new_signal': 'New signal generated',
    'notifications.alert_triggered': 'Alert triggered',

    // ---- Auth ----
    'auth.login': 'Login',
    'auth.logout': 'Logout',
    'auth.register': 'Register',
    'auth.profile': 'My Profile',
    'auth.account': 'Account',

    // ---- Tooltips ----
    'tooltip.collapse_sidebar': 'Collapse sidebar',
    'tooltip.expand_sidebar': 'Expand sidebar',
    'tooltip.toggle_language': 'Toggle language',
    'tooltip.notifications': 'Notifications',
    'tooltip.user_menu': 'User menu',

    // ---- Timeframes ----
    'timeframe.1m': '1 Minute',
    'timeframe.5m': '5 Minutes',
    'timeframe.15m': '15 Minutes',
    'timeframe.1h': '1 Hour',
    'timeframe.4h': '4 Hours',
    'timeframe.1d': '1 Day',
    'timeframe.1w': '1 Week',

    // ---- Empty States ----
    'empty.signals': 'No signals yet',
    'empty.signals_desc': 'New signals will appear here when generated',
    'empty.watchlist': 'Watchlist is empty',
    'empty.watchlist_desc': 'Add assets you want to track',
    'empty.alerts': 'No alerts set',
    'empty.alerts_desc': 'Create alerts to stay informed about price movements',
    'empty.portfolio': 'Portfolio is empty',
    'empty.portfolio_desc': 'Add assets to build your portfolio',
  },
} as const;

export type Translations = typeof translations;

export function getTranslation(lang: Language, key: TranslationKey): string {
  return translations[lang][key] || key;
}

export function t(lang: Language, key: TranslationKey): string {
  return getTranslation(lang, key);
}

export { translations };
export default translations;
