// pages/result/result.js — 日志展示页
const app = getApp();

Page({
  data: {
    diary: null,
    loading: true,
    hasDiary: false,
    isEmpty: false,
    cityDisplay: '',
    photoCount: 0,
    keywordItems: [],
    contentParagraphs: [],
    photoSummaries: [],
    hasWeather: false,
    hasPlaceIntro: false,
    weatherText: '',
    placeIntroText: '',
  },

  onLoad() {
    const diary = app.globalData.currentDiary;
    if (diary) {
      this.setDiaryData(diary);
    } else {
      this.loadLatestDiary();
    }
  },

  setDiaryData(diary) {
    // 所有计算都在 JS 层完成，WXML 只做纯绑定
    const contentParagraphs = diary.content
      ? diary.content.split('\n\n').filter(p => p.trim()).map(p => ({ text: p }))
      : [];

    const keywordItems = (diary.keywords || []).map(keyword => ({ text: keyword }));
    const hasKeywords = keywordItems.length > 0;
    const hasPhotos = diary.photo_summaries && diary.photo_summaries.length > 0;
    const cityDisplay = diary.city || '未知城市';
    const photoCount = diary.photo_count || (diary.photo_summaries ? diary.photo_summaries.length : 0);
    const weatherText = diary.weather_summary || '';
    const placeIntroText = diary.place_intro || '';
    const hasWeather = !!weatherText;
    const hasPlaceIntro = !!placeIntroText;

    // 为每张照片预计算展示字段
    const photoSummaries = (diary.photo_summaries || []).map((p, i) => Object.assign({}, p, {
      index: i + 1,
      hasTime: !!p.taken_time,
      hasCity: !!p.city,
      hasPlace: !!(p.place_name || p.address),
      hasDesc: !!p.diary_sentence,
      hasTags: !!(p.scene_type || p.activity || p.mood),
      timeSourceText: this.formatSource(p.time_source),
      locationSourceText: this.formatSource(p.location_source),
      placeText: p.place_name || p.address || '',
    }));

    this.setData({
      diary: diary,
      contentParagraphs,
      keywordItems,
      hasKeywords,
      hasPhotos,
      cityDisplay,
      photoCount,
      photoSummaries,
      weatherText,
      placeIntroText,
      hasWeather,
      hasPlaceIntro,
      loading: false,
      hasDiary: true,
      isEmpty: false,
    });
  },

  formatSource(source) {
    const map = {
      exif: 'EXIF',
      user: '用户选择',
      ai: 'AI推测',
      unknown: '未知',
    };
    return map[source] || '未知';
  },

  setEmptyState() {
    this.setData({
      diary: null,
      loading: false,
      hasDiary: false,
      isEmpty: true,
      cityDisplay: '',
      photoCount: 0,
      keywordItems: [],
      contentParagraphs: [],
      photoSummaries: [],
      hasWeather: false,
      hasPlaceIntro: false,
      weatherText: '',
      placeIntroText: '',
    });
  },

  async loadLatestDiary() {
    const { request } = require('../../utils/request');
    try {
      const res = await request('/diary/', 'GET');
      if (res.success && res.diaries.length > 0) {
        const latestId = res.diaries[0].id;
        const detail = await request(`/diary/${latestId}`, 'GET');
        if (detail.success) {
          this.setDiaryData(detail.diary);
        } else {
          this.setEmptyState();
        }
      } else {
        this.setEmptyState();
      }
    } catch (err) {
      console.error('加载日志失败:', err);
      this.setEmptyState();
    }
  },

  goHome() {
    wx.reLaunch({ url: '/pages/index/index' });
  },

  goToMap() {
    wx.navigateTo({ url: '/pages/map/map' });
  },
});
