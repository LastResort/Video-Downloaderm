"""
scrollable_table_frame.py

具備水平與垂直雙向捲軸的容器，供 Page2 的播放清單表格使用。

問題背景：
    customtkinter 的 CTkScrollableFrame 在 orientation="vertical" 時，
    會在每次 <Configure> 事件把內層 frame 的寬度強制設為畫布寬度：

        def _fit_frame_dimensions_to_canvas(self, event):
            if self._orientation == "vertical":
                self._parent_canvas.itemconfigure(
                    self._create_window_id,
                    width=self._parent_canvas.winfo_width())

    這代表內容永遠無法在水平方向溢出，也就不可能出現水平捲軸。
    再加上 CTkTable.draw_table() 會對每一欄設 grid_columnconfigure(weight=1)，
    所有欄位只能平均瓜分這個固定寬度，導致長標題頭尾都被截斷。

本類別的作法：
    1. 覆寫 _fit_frame_dimensions_to_canvas，改為「只在內容比視窗窄時才拉寬」。
       內容較寬時放手不管，讓它自然溢出以啟用水平捲動。
    2. 於畫布下方追加一條水平 CTkScrollbar，接到 canvas 的 xview。

相依性注意：
    上述作法必須存取 CTkScrollableFrame 的私有屬性
    (_parent_frame / _parent_canvas / _create_window_id)。
    這些是 customtkinter 的內部實作，未來版本可能變動，
    因此所有存取都包在 try/except 內；一旦結構改變，
    本類別會靜默退回 CTkScrollableFrame 的原始行為（僅垂直捲動），
    而不是讓整個應用程式崩潰。
"""

import customtkinter as ctk

from logging_config import setup_logger

logger = setup_logger(__name__)


class ScrollableTableFrame(ctk.CTkScrollableFrame):
    """垂直捲動（繼承自父類別）+ 水平捲動（本類別追加）的容器。"""

    def __init__(self, master, **kwargs):
        super().__init__(master, orientation="vertical", **kwargs)

        self._hbar = None
        self._hscroll_ready = False

        try:
            self._build_horizontal_scrollbar()
            self._hscroll_ready = True
        except Exception as e:
            # customtkinter 內部結構與預期不符，退回純垂直捲動
            logger.warning(
                "Horizontal scrollbar unavailable, falling back to "
                "vertical-only scrolling (%s)", e)

    # ------------------------------------------------------------------
    # 建立水平捲軸
    # ------------------------------------------------------------------
    def _build_horizontal_scrollbar(self):
        canvas = self._parent_canvas
        parent = self._parent_frame

        self._hbar = ctk.CTkScrollbar(
            master=parent,
            orientation="horizontal",
            command=canvas.xview,
        )
        canvas.configure(xscrollcommand=self._hbar.set)

        # 父類別在 vertical 模式下的佈局為：
        #   row=0 label(可選) / row=1 canvas / column=1 垂直捲軸
        # 水平捲軸放到 canvas 正下方，並與 canvas 對齊同一欄。
        info = canvas.grid_info()
        self._hbar.grid(
            row=int(info.get("row", 1)) + 1,
            column=int(info.get("column", 0)),
            sticky="ew",
            padx=int(info.get("padx", 0)) if str(info.get("padx", 0)).isdigit() else 0,
        )

    # ------------------------------------------------------------------
    # 覆寫父類別的寬度綁定
    # ------------------------------------------------------------------
    def _fit_frame_dimensions_to_canvas(self, event):
        """
        父類別會無條件把內層 frame 寬度設成畫布寬度。
        這裡改為只在「內容比畫布窄」時才拉寬，
        讓表格在內容較寬時能夠溢出並觸發水平捲動。
        """
        if not self._hscroll_ready:
            return super()._fit_frame_dimensions_to_canvas(event)

        try:
            canvas_width = self._parent_canvas.winfo_width()
            content_width = self.winfo_reqwidth()

            if content_width < canvas_width:
                # 內容較窄：維持原本填滿視窗的視覺效果
                self._parent_canvas.itemconfigure(
                    self._create_window_id, width=canvas_width)
            else:
                # 內容較寬：解除寬度限制，交給水平捲軸處理
                self._parent_canvas.itemconfigure(
                    self._create_window_id, width=content_width)

            self._parent_canvas.configure(
                scrollregion=self._parent_canvas.bbox("all"))
        except Exception as e:
            logger.warning("Failed to fit frame dimensions: %s", e)
            return super()._fit_frame_dimensions_to_canvas(event)

    # ------------------------------------------------------------------
    def refresh_scrollregion(self):
        """
        表格內容變動（新增/刪除列）後重算捲動範圍。

        父類別是靠內層 frame 的 <Configure> 事件更新 scrollregion，
        但一次建立上百個 widget 時該事件會被合併或延後，導致捲動範圍
        仍停留在舊值——畫面上的表現就是「要先拖一下捲軸內容才出現」。
        這裡改為排進 idle 佇列，等 Tk 完成所有佈局後再重算一次。
        """
        try:
            self.after_idle(self._do_refresh_scrollregion)
        except Exception as e:
            logger.debug("refresh_scrollregion skipped: %s", e)

    def _do_refresh_scrollregion(self):
        try:
            self.update_idletasks()
            self._fit_frame_dimensions_to_canvas(None)
            self._parent_canvas.configure(
                scrollregion=self._parent_canvas.bbox("all"))
        except Exception as e:
            logger.debug("scrollregion recalculation skipped: %s", e)
