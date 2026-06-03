// pages/result/result.js — 日志展示页
const app = getApp();

Page({
  data: {
    diary: null,
    photos: [],
    loading: true,
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
      ? diary.content.split('\n\n').filter(p => p.trim())
      : [];

    const hasKeywords = diary.keywords && diary.keywords.length > 0;
    const hasPhotos = diary.photo_summaries && diary.photo_summaries.length > 0;
    const cityDisplay = diary.city || '未知城市';
    const photoCount = diary.photo_count || (diary.photo_summaries ? diary.photo_summaries.length : 0);

    // 为每张照片预计算展示字段
    const photoSummaries = (diary.photo_summaries || []).map((p, i) => ({
      ...p,
      index: i + 1,
      hasTime: !!p.taken_time,
      hasCity: !!p.city,
      hasDesc: !!p.diary_sentence,
      hasTags: !!(p.scene_type || p.activity || p.mood),
    }));

    this.setData({
      diary: diary,
      contentParagraphs: contentParagraphs,
      hasKeywords: hasKeywords,
      hasPhotos: hasPhotos,
      cityDisplay: cityDisplay,
      photoCount: photoCount,
      photoSummaries: photoSummaries,
      loading: false,
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
        }
      } else {
        this.setData({ loading: false });
      }
    } catch (err) {
      console.error('加载日志失败:', err);
      this.setData({ loading: false });
    }
  },

  goHome() {
    wx.reLaunch({ url: '/pages/index/index' });
  },

  goToMap() {
    wx.navigateTo({ url: '/pages/map/map' });
  },
});
