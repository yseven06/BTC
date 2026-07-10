import React from "react";
import clsx from "clsx";

/**
 * Statik yükleme iskeleti (PI-1e) — sinyal-DIŞI loading için içerik-şekilli gri blok.
 * Bible-uyumlu: shimmer YOK, sonsuz-pulse YOK (MO-06). Motion taşımaz → reduced-motion
 * nötr. Yüzey +1 lüminans (bg-e-2) → E1 kart üzerinde placeholder olarak okunur.
 *
 * NOT: Sinyal-bağlamı loading boş-Karot kullanır (Karot = AI/konsensüs kimliği; jenerik
 * "yükleniyor" göstergesi DEĞİL). Skeleton yalnız sinyal-dışı yüzeyler içindir.
 *
 * Dekoratif (aria-hidden); saran kapsayıcı `role="status"` + `aria-busy` taşımalıdır.
 * İçerik-şekilli iskelet birden çok Skeleton'ın farklı boyutlarla dizilmesiyle kurulur.
 */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden className={clsx("bg-e-2 rounded-md", className)} {...props} />;
}

export default Skeleton;
