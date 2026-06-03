// pages/analyzing/analyzing.js — AI 分析进度页
const app = getApp();
const { request } = require('../../utils/request');

Page({
  data: {
    currentStep: 0,        // 0-3: upload, exif, ai, diary
    steps: [
      { title: '读取照片信息', desc: '解析 EXIF 时间和 GPS', status: 'pending' },
      { title: 'AI 图片分析', desc: '识别场景、活动、氛围', status: 'pending' },
      { title: '生成游玩日志', desc: '整理照片并生成日记', status: 'pending' },
    ],
    isAnalyzing: false,
    isDone: false,
    diaryId: null,
    errorMessage: '',
  },

  onLoad() {
    this.startAnalysis();
  },

  async startAnalysis() {
    const photoIds = app.globalData.uploadedPhotoIds;
    if (!photoIds || photoIds.length === 0) {
      wx.showToast({ title: '没有需要分析的照片', icon: 'none' });
      setTimeout(() => wx.navigateBack(), 1500);
      return;
    }

    this.setData({ isAnalyzing: true, currentStep: 0 });
    this.updateStep(0, 'active');

    try {
      // ---- Step 1: EXIF 已在后端 upload 时读取，这里主要是 AI 分析 ----
      this.updateStep(0, 'done');
      this.updateStep(1, 'active');
      this.setData({ currentStep: 1 });

      // 调用分析接口
      const analyzeResult = await request('/analyze', 'POST', {
        photo_ids: photoIds,
        geocode: true,
      });

      if (!analyzeResult.success && analyzeResult.errors.length > 0) {
        console.warn('部分分析失败:', analyzeResult.errors);
      }

      this.updateStep(1, 'done');
      this.updateStep(2, 'active');
      this.setData({ currentStep: 2 });

      // ---- Step 2: 生成游玩日志 ----
      const diaryResult = await request('/diary/generate', 'POST', {
        photo_ids: photoIds,
      });

      this.updateStep(2, 'done');
      this.setData({ currentStep: 3, isDone: true, diaryId: diaryResult.diary_id });

      // 保存结果
      app.globalData.currentDiary = diaryResult;

      // 跳转到结果页
      setTimeout(() => {
        wx.redirectTo({ url: '/pages/result/result' });
      }, 800);

    } catch (err) {
      console.error('分析失败:', err);
      this.setData({
        isAnalyzing: false,
        errorMessage: err.message || '分析失败，请检查后端是否正常运行',
      });
    }
  },

  updateStep(index, status) {
    const steps = this.data.steps;
    steps[index].status = status;
    this.setData({ steps });
  },

  goBack() {
    wx.navigateBack();
  },

  retry() {
    this.setData({ errorMessage: '', currentStep: 0 });
    this.startAnalysis();
  },
});
