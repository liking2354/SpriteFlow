import { useState, useEffect } from "react";
import axios from "axios";

/**
 * 根据选中的模型和表单参数，调用后端 /api/calculate_cost 计算 token 消耗
 *
 * @param {Object} selectedModel - 当前选中的模型 { id, name }
 * @param {Object} formValues    - 表单参数对象，可能包含 width, height, resolution, duration 等
 * @returns {{ generationCost: number|null, costDetails: Object|null, isRefreshingCost: boolean }}
 */
export const useGenerationCost = (selectedModel, formValues) => {
  const [generationCost, setGenerationCost] = useState(null);
  const [costDetails, setCostDetails] = useState(null);
  const [isRefreshingCost, setIsRefreshingCost] = useState(false);

  useEffect(() => {
    if (!selectedModel?.id || selectedModel.id.includes("passthrough")) {
      setGenerationCost(null);
      setCostDetails(null);
      return;
    }

    const delayDebounce = setTimeout(() => {
      setIsRefreshingCost(true);

      // 推断模型类型
      const modelId = selectedModel.id.toLowerCase();
      let modelType = "text2img";
      let subModel = "standard";

      // 判断是否为视频模型
      if (
        modelId.includes("video") ||
        modelId.includes("t2v") ||
        modelId.includes("i2v") ||
        modelId.includes("seedance") ||
        modelId.includes("veo") ||
        modelId.includes("kling") ||
        modelId.includes("hunyuan") && !modelId.includes("image")
      ) {
        modelType = modelId.includes("i2v") || modelId.includes("image-to-video") ? "img2video" : "text2video";
      }

      // 判断子模型类型
      if (modelId.includes("fast") || modelId.includes("turbo") || modelId.includes("express")) {
        subModel = "express";
      } else if (modelId.includes("sora")) {
        subModel = "sora2";
      }

      const payload = {
        model_type: modelType,
        sub_model: subModel,
      };

      // 提取尺寸/分辨率参数
      if (formValues) {
        if (formValues.width != null || formValues.height != null) {
          payload.width = formValues.width || 1024;
          payload.height = formValues.height || 1024;
        }
        if (formValues.resolution) {
          payload.resolution = formValues.resolution;
        }
        if (formValues.duration != null) {
          payload.duration = formValues.duration;
        }
      }

      // 如果没有提供宽高但又是图片类型，使用默认尺寸
      if (modelType === "text2img" && payload.width == null) {
        payload.width = 1024;
        payload.height = 1024;
      }

      // 视频类型没有 resolution 时使用默认 720p
      if ((modelType === "text2video" || modelType === "img2video") && !payload.resolution) {
        payload.resolution = "720p";
      }

      axios
        .post("/api/calculate_cost", payload)
        .then((response) => {
          const data = response.data;
          setGenerationCost(data.token_usage ?? data.cost ?? null);
          setCostDetails(data);
          setIsRefreshingCost(false);
        })
        .catch((error) => {
          console.error("Error fetching cost:", error);
          setGenerationCost(null);
          setCostDetails(null);
          setIsRefreshingCost(false);
        });
    }, 500);

    return () => clearTimeout(delayDebounce);
  }, [selectedModel?.id, formValues]);

  return { generationCost, costDetails, isRefreshingCost };
};
