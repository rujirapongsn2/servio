"use client";

import { Suspense } from "react";
import WidgetContent from "@/components/WidgetContent";

export default function WidgetPage() {
    return (
        <div className="w-full h-dvh min-h-0 overflow-hidden bg-[#eaf1fb]" data-color-scheme="light"><Suspense fallback={<div role="status" className="p-4 text-sm text-[#536a7d]">กำลังโหลด…</div>}>
            <WidgetContent />
        </Suspense></div>
    );
}
