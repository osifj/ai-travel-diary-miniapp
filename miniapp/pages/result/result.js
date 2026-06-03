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
      this.setData({
        diary: diary,
        photos: diary.photo_summaries || [],
        loading: false,
      });
    } else {
      // 尝试从后端获取最近的日志
      this.loadLatestDiary();
    }
  },

  async loadLatestDiary() {
    const { request } = require('../../utils/request');
    try {
      const res = await request('/diary/', 'GET');
      if (res.success && res.diaries.length > 0) {
        const latestId = res.diaries[0].id;
        const detail = await request(`/diary/${latestId}`, 'GET');
        if (detail.success) {
          this.setData({
            diary: detail.diary,
            photos: detail.photos || [],
            loading: false,
          });
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
